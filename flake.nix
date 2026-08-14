{
  # Keep this line accurate and one line long: `nix flake metadata` prints it,
  # and it is the first thing a cold agent learns about the repo.
  description = "streamer-verification -- Discord bot that verifies Twitch streamers over dual OAuth and flags impersonators. Run `nix flake show` for the command map.";

  # nixpkgs is the only input, on purpose.
  #
  # flake-utils would buy exactly one thing here -- eachDefaultSystem -- which is
  # the three-line genAttrs below. In exchange it costs a second lock node in
  # every repo (flake-utils transitively pulls `systems`), a second upstream that
  # can break this repo on its own schedule, and a hardcoded system list this
  # repo cannot edit. That list is currently broken: it still contains
  # x86_64-darwin, which now throws (see `systems` below).
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    # `...` rather than a closed { self, nixpkgs }: adding a second input later
    # would otherwise fail with "called with unexpected argument 'self'".
    { nixpkgs, ... }:
    let
      lib = nixpkgs.lib;

      # x86_64-darwin is deliberately absent: nixpkgs 26.11 replaced that whole
      # attribute set with a `throw`. genAttrs is lazy, so plain `nix develop` on
      # Linux would not notice -- it detonates on `nix flake check --all-systems`.
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];

      forAllSystems = f: lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      # ======================================================================
      # PER-REPO BLOCK 1 -- the toolchain
      # ======================================================================
      # python311 and not python313, because every other statement of intent in
      # this repo says 3.11: pyproject's `requires-python = ">=3.11"`, ruff's
      # `target-version = "py311"`, mypy's `python_version = "3.11"`,
      # docker/Dockerfile's `python:3.11-slim`, and .github/workflows/ci.yml's
      # setup-python 3.11. requirements.txt also pins Pillow==10.4.0, which
      # predates CPython 3.13 and ships no cp313 wheel, so a newer interpreter
      # would silently move `dev-setup` from "install wheels" to "compile Pillow
      # from source".
      #
      # ruff, black and mypy are deliberately NOT here even though nixpkgs has
      # them. requirements-dev.txt pins ruff==0.14.9, black==25.1.0 and
      # mypy==1.19.1, and CI gates on exactly those; nixpkgs currently carries
      # much newer ones. Two linters on one tree means `dev-lint` disagreeing
      # with CI for reasons no agent can see, so the lint/fmt commands below call
      # the pinned copies in .venv instead. Do not "fix" this by adding
      # pkgs.ruff: that puts a second, different ruff first on PATH.
      toolchain = pkgs: [
        # ---- this repo's ecosystem ----
        pkgs.python311
        pkgs.uv

        # ---- the bot talks to PostgreSQL over asyncpg ----
        # Matches docker-compose's postgres:15-alpine. asyncpg ships its own
        # protocol implementation and needs no libpq, so this is here for the
        # client tooling an agent actually reaches for: psql, pg_isready, and
        # pg_ctl/initdb for a throwaway local database when Docker is not
        # available.
        pkgs.postgresql_15

        # ---- present in every repo in the fleet ----
        pkgs.git
        pkgs.jq
        pkgs.gnumake
      ];

      # ======================================================================
      # PER-REPO BLOCK 2 -- libraries that get dlopened, not linked
      # ======================================================================
      # The wheels this repo installs (asyncpg, Levenshtein, rapidfuzz, Pillow,
      # pydantic-core) are manylinux builds whose .so files are dlopened, so
      # neither patchelf nor the nix linker ever sees them and NixOS has no
      # /usr/lib for them to find. stdenv.cc.cc.lib supplies libstdc++, which is
      # the one that breaks the C++-built extensions. Keep this list minimal --
      # LD_LIBRARY_PATH is a blunt instrument.
      nativeLibs = pkgs: [
        pkgs.stdenv.cc.cc.lib
        pkgs.zlib
      ];

      # ======================================================================
      # PER-REPO BLOCK 3 -- constant environment variables
      # ======================================================================
      # Only constants belong here. Anything that must READ an existing value
      # (LD_LIBRARY_PATH), UNSET something (SOURCE_DATE_EPOCH) or depend on the
      # work tree (PYTHONPATH, which needs $REPO_ROOT) lives further down.
      #
      # Note what is NOT here: the bot's own configuration. src/config.py is a
      # pydantic-settings model with a dozen required fields, and it reads `.env`
      # from the current directory. Baking placeholder tokens into the shell
      # would take precedence over that file (environment beats .env in
      # pydantic-settings) and quietly point a real `dev-run` at fake
      # credentials. The test-only placeholders live inside `commands.test`.
      envVars = pkgs: {
        # Keep uv on the nix interpreter. Left alone it downloads its own
        # portable CPython, which then resolves a different set of wheels than
        # this shell pins: two Pythons, one venv, no way to tell which is live.
        UV_PYTHON = "${pkgs.python311}/bin/python";
        UV_PYTHON_DOWNLOADS = "never";
        # /nix/store and the work tree are usually different filesystems, so
        # uv's default hardlink strategy warns on every single install.
        UV_LINK_MODE = "copy";
        PIP_DISABLE_PIP_VERSION_CHECK = "1";
      };

      # ======================================================================
      # PER-REPO BLOCK 4 -- the command map
      # ======================================================================
      # THE single source of truth: it generates `apps` (so `nix run .#test`
      # works), the `dev-*` wrappers on PATH inside the shell, and `dev-help`.
      #
      # No `build` verb: this repo produces no artifact. The deployable thing is
      # a container image built by .github/workflows/docker-build.yml from
      # docker/Dockerfile, which needs a Docker daemon rather than a nix shell.
      # Absence is information -- a stub that echoed "not applicable" would turn
      # the command map into a liar.
      #
      # Every command below reaches its Python tools through
      # "$REPO_ROOT/.venv/bin/...". That is not a style choice: the wrappers
      # PREPEND the nix toolchain to PATH, so a bare `pytest` or `ruff` would
      # resolve to a store copy and miss everything `dev-setup` installed.
      commands = pkgs: {
        setup = {
          description = "(network) create .venv and install requirements-dev.txt";
          # requirements-dev.txt starts with `-r requirements.txt`, so this one
          # install covers the runtime deps too -- same as CI, which installs
          # both files.
          text = ''
            uv venv "$REPO_ROOT/.venv"
            uv pip install --python "$REPO_ROOT/.venv/bin/python" -r "$REPO_ROOT/requirements-dev.txt" "$@"
          '';
        };

        test = {
          description = "run the pytest suite (needs `setup` first)";
          text = ''
            # src/config.py is instantiated at import time and every field below
            # is required, so without these the suite dies during collection
            # with a pydantic ValidationError rather than a test failure. These
            # are the exact placeholders .github/workflows/ci.yml exports, and
            # the `:-` form means a real value already in the environment wins.
            # The tests themselves mock every I/O boundary; nothing here dials
            # out and no PostgreSQL needs to be running.
            export DISCORD_BOT_TOKEN="''${DISCORD_BOT_TOKEN:-test_token}"
            export DISCORD_OAUTH_CLIENT_ID="''${DISCORD_OAUTH_CLIENT_ID:-test_id}"
            export DISCORD_OAUTH_CLIENT_SECRET="''${DISCORD_OAUTH_CLIENT_SECRET:-test_secret}"
            export DISCORD_OAUTH_REDIRECT_URI="''${DISCORD_OAUTH_REDIRECT_URI:-http://localhost:8080/linked-role}"
            export DISCORD_LINKED_ROLE_VERIFICATION_URL="''${DISCORD_LINKED_ROLE_VERIFICATION_URL:-http://localhost:8080/linked-role}"
            export TWITCH_CLIENT_ID="''${TWITCH_CLIENT_ID:-test_id}"
            export TWITCH_CLIENT_SECRET="''${TWITCH_CLIENT_SECRET:-test_secret}"
            export TWITCH_REDIRECT_URI="''${TWITCH_REDIRECT_URI:-http://localhost:8080/twitch-callback}"
            export WEB_BASE_URL="''${WEB_BASE_URL:-http://localhost:8080}"
            export DATABASE_HOST="''${DATABASE_HOST:-localhost}"
            export DATABASE_PORT="''${DATABASE_PORT:-5432}"
            export DATABASE_NAME="''${DATABASE_NAME:-test_db}"
            export DATABASE_USER="''${DATABASE_USER:-test_user}"
            export DATABASE_PASSWORD="''${DATABASE_PASSWORD:-test_pass}"

            # Both halves of this invocation were arrived at empirically, and
            # neither is sufficient alone. -c makes pytest read
            # [tool.pytest.ini_options] out of pyproject.toml no matter where it
            # was invoked from. The explicit tests path is what anchors rootdir
            # and collection: `testpaths = ["tests"]` is resolved against the
            # caller's directory, not against the config file, so `dev-test` from
            # a subdirectory reported "collected 0 items / no tests ran" -- exit
            # code 0 on a suite that never executed, which is the worst possible
            # answer to give an agent. --rootdir does not fix it either.
            # Arguments passed by the caller replace the default target.
            if [ "$#" -eq 0 ]; then
              set -- "$REPO_ROOT/tests"
            fi
            "$REPO_ROOT/.venv/bin/python" -m pytest -c "$REPO_ROOT/pyproject.toml" "$@"
          '';
        };

        lint = {
          description = "black --check + ruff + mypy over src/, exactly as CI (needs `setup` first)";
          text = ''
            # Same three gates, same order, same pinned tools as the
            # lint-and-test job in .github/workflows/ci.yml. set -e stops at the
            # first failure, which is also how CI reports.
            if [ "$#" -eq 0 ]; then
              set -- "$REPO_ROOT/src"
            fi
            "$REPO_ROOT/.venv/bin/black" --check "$@"
            "$REPO_ROOT/.venv/bin/ruff" check "$@"
            "$REPO_ROOT/.venv/bin/mypy" --config-file "$REPO_ROOT/pyproject.toml" --ignore-missing-imports "$@"
          '';
        };

        fmt = {
          description = "black + ruff --fix (rewrites files, needs `setup` first)";
          text = ''
            # Mirrors .pre-commit-config.yaml: black first, then ruff's
            # autofixes. black is the formatter CI gates on, so ruff format must
            # never be substituted here -- the two disagree and CI would reject
            # the result.
            if [ "$#" -eq 0 ]; then
              set -- "$REPO_ROOT/src" "$REPO_ROOT/tests" "$REPO_ROOT/scripts"
            fi
            "$REPO_ROOT/.venv/bin/black" "$@"
            "$REPO_ROOT/.venv/bin/ruff" check --fix "$@"
          '';
        };

        run = {
          description = "start the bot and its web server (needs `setup`, a .env and a reachable PostgreSQL)";
          text = ''
            # PYTHONPATH is load-bearing, not decoration: src/main.py does
            # `from src.config import config`, and running a script puts the
            # SCRIPT's directory (src/) on sys.path -- never the repo root. The
            # Dockerfile solves this with ENV PYTHONPATH=/app; this is the same
            # fix, anchored so it also works from a subdirectory.
            export PYTHONPATH="$REPO_ROOT''${PYTHONPATH:+:$PYTHONPATH}"
            exec "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/src/main.py" "$@"
          '';
        };
      };

      # ======================================================================
      # GENERIC MACHINERY -- byte-identical in all 41 repos, do not edit
      # ======================================================================

      # Prepend, never assign: a host LD_LIBRARY_PATH may be carrying something
      # the user needs, and clobbering it breaks binaries they launch from here.
      # Linux only -- on darwin the loader variable is DYLD_*, and exporting a
      # Linux-shaped value there is at best useless.
      ldPreamble =
        pkgs:
        lib.optionalString (pkgs.stdenv.hostPlatform.isLinux && nativeLibs pkgs != [ ]) ''
          export LD_LIBRARY_PATH="${lib.makeLibraryPath (nativeLibs pkgs)}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        '';

      # Every command gets $REPO_ROOT. `nix run` and `nix develop` both start in
      # whatever directory they were invoked from, so a bare `.venv` silently
      # forks a second environment as soon as an agent works from a subdirectory.
      # Note we do NOT cd there: commands act on the caller's cwd on purpose.
      rootPreamble = ''
        REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
        export REPO_ROOT
      '';

      # One derivation per command, reused by both `apps` and the dev shell, so
      # the two can never diverge. `dev-` prefixed because a bare `test` binary
      # earlier on PATH would shadow the POSIX shell builtin and quietly break
      # every script in the repo that uses it.
      wrappers =
        pkgs:
        lib.mapAttrs (
          name: cmd:
          pkgs.writeShellApplication {
            name = "dev-${name}";
            runtimeInputs = toolchain pkgs;
            runtimeEnv = envVars pkgs;
            meta.description = cmd.description;
            text = ''
              ${rootPreamble}
              ${ldPreamble pkgs}
              ${cmd.text}
            '';
          }
        ) (commands pkgs);

      helpFor =
        pkgs:
        let
          cmds = commands pkgs;
          names = lib.attrNames cmds;
          width = lib.foldl' (a: n: lib.max a (builtins.stringLength n)) 0 names;
          pad = n: n + lib.concatStrings (lib.genList (_: " ") (width - builtins.stringLength n));
          line = n: c: "  dev-${pad n}  ${c.description}";
        in
        pkgs.writeShellApplication {
          name = "dev-help";
          meta.description = "print this repo's command map (works offline)";
          text = ''
            cat <<'EOF'
            ${lib.concatStringsSep "\n" (lib.mapAttrsToList line cmds)}
            EOF
          '';
        };
    in
    {
      # `nix flake show` -- the discovery entrypoint, and deliberately the whole
      # machine-facing contract: every app carries a meta.description, which
      # `nix flake show` prints inline and `nix flake show --json` exposes at
      # .apps.<system>.<name>.description. Pure evaluation, so an agent gets the
      # entire command map in one cheap call without reading a README.
      apps = forAllSystems (
        pkgs:
        lib.mapAttrs (name: cmd: {
          type = "app";
          program = "${(wrappers pkgs).${name}}/bin/dev-${name}";
          meta.description = cmd.description;
        }) (commands pkgs)
      );

      # `nix develop` -- the toolchain, plus a dev-<verb> for every app.
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = toolchain pkgs ++ lib.attrValues (wrappers pkgs) ++ [ (helpFor pkgs) ];

          env = envVars pkgs;

          # Some C extensions compile at -O0, where glibc's _FORTIFY_SOURCE
          # becomes a hard error instead of a warning.
          hardeningDisable = [ "fortify" ];

          shellHook = ''
            # mkShell inherits SOURCE_DATE_EPOCH=315532800 (1980-01-01) from
            # stdenv, and any wheel or zip built in here then dies with "ZIP does
            # not support timestamps before 1980".
            unset SOURCE_DATE_EPOCH

            ${rootPreamble}
            ${ldPreamble pkgs}

            # Nothing networked, nothing stateful and nothing interactive above
            # this line, and nothing below it either. No venv creation, no
            # `pip install`, no `pre-commit install`, no `read`, no `exec $SHELL`.
            # Bootstrapping in the hook makes a cold `nix develop -c pytest`
            # start downloading before it runs anything, on EVERY invocation --
            # the exact failure an unattended agent cannot diagnose. That is what
            # `dev-setup` is for.
            #
            # Note we also do not activate .venv here. It would make the same
            # command behave differently inside `nix develop` (venv python first
            # on PATH) and under `nix run` (store python first); the absolute
            # "$REPO_ROOT/.venv/bin/python" in every command text behaves
            # identically on both surfaces.

            # The banner is interactive-only, and this guard is load-bearing:
            # shellHook output lands on the STDOUT of `nix develop -c <cmd>`, so
            # an unguarded echo corrupts anything parsing it
            # (`nix develop -c cat x.json | jq` fails to parse). $- is the only
            # reliable discriminator -- it lacks `i` for `nix develop -c` and has
            # it at an interactive prompt, while `[ -t 1 ]` still passes when an
            # agent harness allocates a pty. Do not test $PS1 (unset in both) or
            # $IN_NIX_SHELL (set in both). >&2 is the second layer.
            case $- in
              *i*) echo "streamer-verification dev shell -- 'dev-help' for the command map" >&2 ;;
            esac
          '';
        };
      });

      # `nix flake check` -- honest by construction. It realises the toolchain
      # closure (so a typo'd or currently-broken attr fails here) and builds
      # every wrapper, which runs shellcheck over every command text. NEVER add
      # a check that always passes: an agent reads "all checks passed!" as a
      # signal, and a fake check makes `nix flake check` a liar.
      checks = forAllSystems (pkgs: {
        toolchain =
          pkgs.runCommand "toolchain-check"
            {
              nativeBuildInputs = toolchain pkgs ++ lib.attrValues (wrappers pkgs);
            }
            ''
              for verb in ${lib.escapeShellArgs (lib.attrNames (commands pkgs))}; do
                command -v "dev-$verb" > /dev/null || {
                  echo "dev-$verb is not on PATH" >&2
                  exit 1
                }
              done
              touch "$out"
            '';
      });

      # `nix fmt` -- formats the *Nix* in this repo; project code is `dev-fmt`.
      # nixfmt-tree (the treefmt wrapper) rather than bare nixfmt, because bare
      # nixfmt tries to parse every path handed to it and fails on non-Nix files.
      formatter = forAllSystems (pkgs: pkgs.nixfmt-tree);
    };
}
