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
chat_files = []
ranked_tags, file_report = repo_map.get_ranked_tags(chat_files, other_files)

# Generate the actual map content
map_content, file_report = repo_map.get_repo_map(chat_files=chat_files, other_files=other_files, force_refresh=False)

print(f'Map tokens: {count_tokens(map_content, "gpt-4")}')
print(f'Coverage: {file_report.coverage_pct}%')

# Check if IEx is in the map content
iex_in_map = 'IEx' in map_content
configure_in_map = 'configure' in map_content
configuration_in_map = 'configuration' in map_content
print(f'IEx in map: {iex_in_map}')
print(f'configure in map: {configure_in_map}')
print(f'configuration in map: {configuration_in_map}')

# Show first 5000 chars of map
print(f'\n--- First 5000 chars of map ---')
print(map_content[:5000])