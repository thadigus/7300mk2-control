{
  description = "IC-7300MK2 remote control station - Python dev shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python312;
      in {
        devShells.default = pkgs.mkShell {
          packages = [ pkgs.uv python pkgs.git ];

          shellHook = ''
            export UV_PYTHON_DOWNLOADS=never
            export UV_PYTHON="${python}/bin/python"
            uv sync --all-packages
            echo "ic7300mk2 dev shell - $(uv --version), $(${python}/bin/python --version)"
            echo "  tests:       uv run pytest ic7300mk2-sdk/tests ic7300mk2-server/tests"
            echo "  run server:  uv run --package ic7300mk2-server ic7300mk2-server"
          '';
        };
      });
}
