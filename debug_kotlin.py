import sys
sys.path.insert(0, '.')
from core import Tricorder
from utils import read_text, count_tokens, discover_src_files

root = r'D:\Projects\Tricorder-Testing-Repos\kotlin'
scan_path = 'core/language.model/src,core/compiler.common.jvm/src'

repo_map = Tricorder(
    map_tokens=8192,
    root=root,
    token_counter_func=lambda text: count_tokens(text, 'gpt-4'),
    file_reader_func=read_text,
    output_handler_funcs={'info': print, 'warning': print, 'error': print},
    verbose=True,
)

other_files = discover_src_files(root + '\\' + scan_path.replace(',', '\\'), use_gitignore=True)
print(f'Other files count: {len(other_files)}')

chat_files = []
ranked_tags, file_report = repo_map.get_ranked_tags(chat_files, other_files)
print(f'Ranked tags count: {len(ranked_tags)}')

# Check for computeExpandedTypeForInlineClass
tags = [t for t in ranked_tags if 'computeExpanded' in t[1].name or 'compute_expanded' in t[1].name or 'ExpandedType' in t[1].name]
print(f'computeExpanded tags in ranked: {len(tags)}')
for t in tags:
    print(f'  {t[1].kind}: {t[1].name} at {t[1].rel_fname}:{t[1].line}')

# Check for Variance
tags2 = [t for t in ranked_tags if 'Variance' in t[1].name]
print(f'Variance tags in ranked: {len(tags2)}')
for t in tags2:
    print(f'  {t[1].kind}: {t[1].name} at {t[1].rel_fname}:{t[1].line}')