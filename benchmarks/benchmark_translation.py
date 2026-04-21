from pathlib import Path
import sys


SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from traductor_tiempo_real.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["benchmark-traduccion", *sys.argv[1:]]))
