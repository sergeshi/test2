#!/usr/bin/env python3
"""LITERA — редактор шрифтов на Python.

Запуск:  python run_litera.py            # пустой редактор
         python run_litera.py --demo     # с демонстрационным проектом
         python run_litera.py file.ttf   # импорт шрифта
         python run_litera.py p.litera.json
Без консольного окна в Windows: pythonw run_litera.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from litera.ui.app import main   # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
