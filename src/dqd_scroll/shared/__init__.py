import json;
from importlib.resources import files;


def load_position_map() -> dict[str, str]:
    # 通过包资源读取，源码运行和安装后的 Python 脚本共用同一份位置映射。
    mapping = json.loads(files(__name__).joinpath('positionMap.json').read_text(encoding='utf-8'));
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError('positionMap.json 必须是非空对象。');
    for name, code in mapping.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(code, str) or not code.strip():
            raise ValueError('positionMap.json 的位置名称和代码必须是非空字符串。');
    return mapping;
