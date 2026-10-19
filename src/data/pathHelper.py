from pathlib import Path


def projectRoot() -> Path:
    '''返回项目根目录（即 src 目录的上一级）。

    Returns:
        Path: 项目根目录的绝对路径。
    '''
    return Path(__file__).resolve().parents[2]
