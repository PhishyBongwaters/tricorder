import sys
sys.path.insert(0, '.')
from core import Tricorder
from utils import read_text, count_tokens, discover_src_files, Tag

root = r'D:\Projects\Tricorder-Testing-Repos\elixir'
scan_path = 'lib'
full = root + '\\' + scan_path

repo_map = Tricorder(
    map_tokens=4000,
    root=root,
    token_counter_func=lambda text: count_tokens(text, 'gpt-4'),
    file_reader_func=read_text,
    output_handler_funcs={'info': print, 'warning': print, 'error': print},
    verbose=True,
)

other_files = discover_src_files(full, use_gitignore=True)
print(f'Other files count: {len(other_files)}')

chat_files = []
ranked_tags, file_report = repo_map.get_ranked_tags(chat_files, other_files)
print(f'Ranked tags count: {len(ranked_tags)}')
print(f'First tag: {ranked_tags[0]}')

iex_tags = [t[1] for t in ranked_tags if 'IEx' in t[1].name or 'configure' in t[1].name or 'configuration' in t[1].name]
print(f'IEx-related tags in ranked: {len(iex_tags)}')
for t in iex_tags:
    print(f'  {t.kind}: {t.name} at {t.rel_fname}:{t.line}')