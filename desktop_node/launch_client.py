"""无控制台窗口启动 Echo Desktop 客户端，供开机自启动使用。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from echo_desktop.gui import main  # noqa: E402

if __name__ == "__main__":
    main()
