import sys
sys.path.insert(0, '.')
from core import Tricorder
tc = Tricorder(root=r'D:\Projects\Tricorder-Testing-Repos\swift', use_db=False, verbose=False)
import json
out = tc.search_identifiers('parseExpr', max_results=8) if hasattr(tc, 'search_identifiers') else None
print(json.dumps(out, default=str)[:1500] if out else 'no search_identifiers')
