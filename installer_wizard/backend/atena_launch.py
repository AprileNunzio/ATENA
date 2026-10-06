import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import safe_mode


def main() -> None:
    try:
        import atena_supervisor
    except BaseException as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
        logging.getLogger("atena.launch").exception("Avvio non riuscito: modalità sicura")
        safe_mode.run(exc)
        return
    safe_mode.clear()
    asyncio.run(atena_supervisor.main())


if __name__ == "__main__":
    main()
