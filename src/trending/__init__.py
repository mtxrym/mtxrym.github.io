"""热榜：移植自 NewsNow（https://github.com/ourongxing/newsnow，MIT 协议）的多平台热榜抓取。

导入本包即完成所有抓取器的注册（FETCHERS），数据源配置见 config/trending_sources.yaml。
"""

from . import china, finance, sports, tech, world  # noqa: F401  导入即注册
from .core import COLUMNS, FETCHERS, FetchError, Http, Item, SourceMeta, load_sources, normalize

__all__ = ["COLUMNS", "FETCHERS", "FetchError", "Http", "Item", "SourceMeta", "load_sources", "normalize"]
