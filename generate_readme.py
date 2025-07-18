import json
import os
from datetime import datetime
import pytz

stats_path = 'LiveTV/Bangladesh/stats.json'
readme_path = 'README.md'
repo_owner_and_name = 'aniketsainiop/AniXLinks'

# Load stats
if os.path.exists(stats_path):
    with open(stats_path, 'r', encoding='utf-8') as f:
        stats = json.load(f)
else:
    stats = {'total_channels': 0, 'total_groups': 0}

# Define README template
readme_template = f'''# 🎬 AniXLinks - Live TV Channels

> **Advanced M3U Playlist Collector by Aniket**
> 
> Follow me on Instagram: [@aniket_aep](https://instagram.com/aniket_aep)

## 📊 Channel Statistics

- 📺 **Total Channels**: {stats.get('total_channels', 0)}
- 📂 **Total Groups**: {stats.get('total_groups', 0)}
- 🕐 **Last Updated**: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S IST')}
- 🔄 **Auto-Updated**: Every 6 hours

## 🚀 Quick Access

### 📱 Direct Links
- **📄 AniXLinks.json**: [Download](https://raw.githubusercontent.com/{repo_owner_and_name}/main/LiveTV/Bangladesh/AniXLinks.json)
- **📺 M3U Playlist**: [Download](https://raw.githubusercontent.com/{repo_owner_and_name}/main/LiveTV/Bangladesh/AniXLinks.m3u)
'''

# Write the new README
with open(readme_path, 'w', encoding='utf-8') as f:
    f.write(readme_template)

print(f"README.md generated successfully with {stats.get('total_channels', 0)} channels.")
