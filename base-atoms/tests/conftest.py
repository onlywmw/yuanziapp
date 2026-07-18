import sys
from pathlib import Path

# base-atoms/tests 不假设单一 core 包；测试用 importlib 按目录加载
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
