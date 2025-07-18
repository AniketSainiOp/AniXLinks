#!/usr/bin/env python3
"""
AniXLinks - Advanced M3U Playlist Collector
A high-performance IPTV playlist aggregator and manager

Author: Aniket (aniket_aep)
GitHub: https://github.com/aniketsainiop/
Instagram: @aniket_aep

Features:
- Multi-source M3U playlist aggregation
- Automatic link validation and cleanup
- Multiple export formats (M3U, JSON, TXT)
- Concurrent processing for speed
- Duplicate removal and optimization
- GitHub Actions compatible
"""

#!/usr/bin/env python3

import requests
import json
import os
import re
import sys
import asyncio
import aiohttp
from urllib.parse import urlparse
from collections import defaultdict
from datetime import datetime
import pytz
import concurrent.futures
import threading
import logging
from bs4 import BeautifulSoup
from typing import Dict, List, Set, Tuple, Optional
import hashlib

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

class AniXLinksCollector:
    def __init__(self, country: str = "Bangladesh", base_dir: str = "LiveTV", check_links: bool = True):
        self.channels = defaultdict(list)
        self.default_logo = "https://via.placeholder.com/100x100.png?text=AniXLinks"
        self.seen_urls: Set[str] = set()
        self.url_status_cache: Dict[str, Tuple[bool, str]] = {}
        self.output_dir = os.path.join(base_dir, country)
        self.lock = threading.Lock()
        self.check_links = check_links
        self.session = None
        self.author_info = {
            "name": "Aniket",
            "instagram": "aniket_aep",
            "github": "https://github.com/aniketsainiop",
            "version": "2.0.2"
        }
        
        print(f"--> AniXLinks Collector by {self.author_info['name']} - GitHub: {self.author_info['github']} <--")
        
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }

    def __enter__(self):
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            self.session.close()

    def generate_channel_id(self, name: str, url: str) -> str:
        combined = f"{name}_{url}".encode('utf-8')
        return hashlib.md5(combined).hexdigest()[:8]

    def fetch_content(self, url: str) -> Tuple[Optional[str], List[str]]:
        max_retries = 3
        timeout = 15
        
        for attempt in range(max_retries):
            try:
                response = self.session.get(
                    url, 
                    stream=True, 
                    timeout=timeout,
                    allow_redirects=True
                )
                response.raise_for_status()
                
                content_type = response.headers.get('content-type', '').lower()
                if 'json' in content_type:
                    content = response.text
                    lines = [content]
                else:
                    lines = []
                    for line_bytes in response.iter_lines():
                        if line_bytes:
                            lines.append(line_bytes.decode('utf-8', errors='ignore').strip())
                    content = '\n'.join(lines)
                
                if lines:
                    logging.info(f"[✓] Fetched {len(lines)} lines from {url}")
                    return content, lines
                else:
                    logging.warning(f"[!] No content from {url}")
                    
            except requests.exceptions.RequestException as e:
                logging.warning(f"[!] Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < max_retries - 1:
                    continue
                else:
                    logging.error(f"[x] Failed to fetch {url} after {max_retries} attempts")
                    
        return None, []

    def extract_stream_urls_from_html(self, html_content: str, base_url: str) -> List[str]:
        if not html_content:
            return []
        
        soup = BeautifulSoup(html_content, 'html.parser')
        stream_urls = set()
        
        selectors = [
            'a[href*=".m3u"]', 'a[href*=".m3u8"]', 'a[href*="playlist"]',
            'a[href*="stream"]', 'script[src*=".m3u"]', 'script[src*=".m3u8"]'
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            for element in elements:
                href = element.get('href') or element.get('src')
                if href:
                    if not href.startswith(('http://', 'https://')):
                        parsed_base = urlparse(base_url)
                        if href.startswith('/'):
                            href = f"{parsed_base.scheme}://{parsed_base.netloc}{href}"
                        else:
                            href = f"{parsed_base.scheme}://{parsed_base.netloc}/{href}"
                    
                    if self.is_valid_stream_url(href):
                        stream_urls.add(href)
        
        try:
            json_data = json.loads(html_content)
            if isinstance(json_data, list):
                for item in json_data:
                    if isinstance(item, dict) and 'url' in item:
                        url = item['url']
                        if self.is_valid_stream_url(url):
                            stream_urls.add(url)
        except (json.JSONDecodeError, TypeError):
            pass
        
        logging.info(f"[✓] Extracted {len(stream_urls)} streaming URLs from {base_url}")
        return list(stream_urls)

    def is_valid_stream_url(self, url: str) -> bool:
        if not url or not isinstance(url, str):
            return False
            
        exclude_patterns = [
            'telegram', '.html', '.php', 'github.com', 'login', 'signup',
            'facebook.com', 'twitter.com', 'instagram.com', 'youtube.com',
            'ads', 'advertising', 'tracker', 'analytics'
        ]
        
        url_lower = url.lower()
        if any(pattern in url_lower for pattern in exclude_patterns):
            return False
        
        valid_patterns = [
            r'\.m3u8?$', r'\.ts$', r'\.mp4$', r'playlist', r'stream',
            r'live', r'rtmp://', r'rtsp://'
        ]
        
        return any(re.search(pattern, url_lower) for pattern in valid_patterns)

    def check_link_active(self, url: str, timeout: int = 5) -> Tuple[bool, str]:
        with self.lock:
            if url in self.url_status_cache:
                return self.url_status_cache[url]
        
        try:
            response = self.session.head(url, timeout=timeout, allow_redirects=True)
            if response.status_code < 400:
                with self.lock:
                    self.url_status_cache[url] = (True, url)
                return True, url
        except requests.RequestException:
            try:
                response = self.session.get(url, timeout=timeout, stream=True, allow_redirects=True)
                if response.status_code < 400:
                    with self.lock:
                        self.url_status_cache[url] = (True, url)
                    return True, url
            except requests.RequestException:
                pass
        
        alt_url = url.replace('https://', 'http://') if url.startswith('https://') else url.replace('http://', 'https://')
        if alt_url != url:
            try:
                response = self.session.head(alt_url, timeout=timeout, allow_redirects=True)
                if response.status_code < 400:
                    with self.lock:
                        self.url_status_cache[url] = (True, alt_url)
                    return True, alt_url
            except requests.RequestException:
                pass
        
        with self.lock:
            self.url_status_cache[url] = (False, url)
        return False, url

    def parse_m3u_content(self, lines: List[str], source_url: str) -> None:
        current_channel = {}
        channel_count = 0
        
        for line in lines:
            line = line.strip()
            
            if line.startswith('#EXTINF:'):
                logo_match = re.search(r'tvg-logo="([^"]*)"', line)
                logo = logo_match.group(1) if logo_match and logo_match.group(1) else self.default_logo
                
                group_match = re.search(r'group-title="([^"]*)"', line)
                group = group_match.group(1) if group_match else "General"
                
                id_match = re.search(r'tvg-id="([^"]*)"', line)
                tvg_id = id_match.group(1) if id_match else ""
                
                name_match = re.search(r',(.+)$', line)
                name = name_match.group(1).strip() if name_match else "Unknown Channel"
                
                name = re.sub(r'\s+', ' ', name).strip()
                
                current_channel = {
                    'id': self.generate_channel_id(name, source_url), 'name': name, 'logo': logo,
                    'group': group, 'tvg_id': tvg_id, 'source': source_url,
                    'added_date': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat()
                }
                
            elif line.startswith(('http://', 'https://', 'rtmp://', 'rtsp://')) and current_channel:
                with self.lock:
                    if line not in self.seen_urls:
                        self.seen_urls.add(line)
                        current_channel['url'] = line
                        self.channels[current_channel['group']].append(current_channel)
                        channel_count += 1
                        
                current_channel = {}
        
        logging.info(f"[✓] Parsed {channel_count} channels from {source_url}")

    def parse_json_content(self, content: str, source_url: str) -> None:
        try:
            data = json.loads(content)
            channel_count = 0
            
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and 'url' in item:
                        name = item.get('name', 'Unknown Channel')
                        url = item.get('url', '')
                        logo = item.get('img', item.get('logo', self.default_logo))
                        group = item.get('type', item.get('category', 'General'))
                        
                        if url and url not in self.seen_urls:
                            self.seen_urls.add(url)
                            channel = {
                                'id': self.generate_channel_id(name, url), 'name': name, 'logo': logo,
                                'group': group, 'tvg_id': '', 'source': source_url, 'url': url,
                                'added_date': datetime.now(pytz.timezone('Asia/Kolkata')).isoformat()
                            }
                            self.channels[group].append(channel)
                            channel_count += 1
            
            logging.info(f"[✓] Parsed {channel_count} channels from JSON: {source_url}")
            
        except json.JSONDecodeError as e:
            logging.error(f"[x] Failed to parse JSON from {source_url}: {e}")

    def filter_active_channels(self) -> None:
        if not self.check_links:
            logging.info("[!] Skipping link validation for faster processing")
            return
        
        logging.info("[?] Starting link validation...")
        active_channels = defaultdict(list)
        all_channels = [(group, ch) for group, chans in self.channels.items() for ch in chans]
        total_channels = len(all_channels)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            future_to_channel = {
                executor.submit(self.check_link_active, ch['url']): (group, ch)
                for group, ch in all_channels
            }
            
            completed = 0
            for future in concurrent.futures.as_completed(future_to_channel):
                group, channel = future_to_channel[future]
                completed += 1
                
                try:
                    is_active, updated_url = future.result()
                    if is_active:
                        channel['url'] = updated_url
                        channel['status'] = 'active'
                        active_channels[group].append(channel)
                    else:
                        channel['status'] = 'inactive'
                        
                    if completed % 50 == 0:
                        logging.info(f"[*] Validated {completed}/{total_channels} channels")
                        
                except Exception as e:
                    logging.error(f"[x] Error validating {channel['url']}: {e}")
        
        active_count = sum(len(ch) for ch in active_channels.values())
        logging.info(f"[✓] Validation complete: {active_count}/{total_channels} channels active")
        self.channels = active_channels

    def process_sources(self, source_urls: List[str]) -> None:
        logging.info(f"[+] Starting to process {len(source_urls)} sources...")
        
        self.channels.clear()
        self.seen_urls.clear()
        self.url_status_cache.clear()
        
        all_m3u_urls = set()
        
        for i, url in enumerate(source_urls, 1):
            logging.info(f"[+] Processing source {i}/{len(source_urls)}: {url}")
            
            content, lines = self.fetch_content(url)
            if not content:
                continue
            
            if url.endswith('.html') or 'html' in url.lower():
                m3u_urls = self.extract_stream_urls_from_html(content, url)
                all_m3u_urls.update(m3u_urls)
            elif url.endswith('.json') or 'json' in content[:100].lower():
                self.parse_json_content(content, url)
            else:
                self.parse_m3u_content(lines, url)
        
        for m3u_url in all_m3u_urls:
            logging.info(f"[+] Processing discovered M3U: {m3u_url}")
            _, lines = self.fetch_content(m3u_url)
            if lines:
                self.parse_m3u_content(lines, m3u_url)
        
        if self.channels:
            self.filter_active_channels()
        else:
            logging.warning("[!] No channels found from any source")

    def export_anixlinks_json(self, filename: str = "AniXLinks.json") -> str:
        filepath = os.path.join(self.output_dir, filename)
        
        ist_tz = pytz.timezone('Asia/Kolkata')
        current_time = datetime.now(ist_tz)
        
        export_data = {
            "meta": {
                "title": "AniXLinks - Live TV Channels",
                "description": "Curated collection of live TV channels from multiple sources",
                "author": self.author_info["name"], "instagram": self.author_info["instagram"], 
                "github": self.author_info["github"], "version": self.author_info["version"],
                "generated_at": current_time.isoformat(),
                "generated_at_readable": current_time.strftime("%Y-%m-%d %H:%M:%S IST"),
                "timezone": "Asia/Kolkata",
                "total_channels": sum(len(channels) for channels in self.channels.values()),
                "total_groups": len(self.channels), "groups": list(self.channels.keys())
            },
            "channels": {}
        }
        
        for group, channels in sorted(self.channels.items()):
            export_data["channels"][group] = [
                {
                    "id": channel["id"], "name": channel["name"], "url": channel["url"],
                    "logo": channel["logo"], "tvg_id": channel.get("tvg_id", ""),
                    "source": channel["source"], "added_date": channel.get("added_date", ""),
                    "status": channel.get("status", "unknown")
                }
                for channel in channels
            ]
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        logging.info(f"[✓] Exported AniXLinks JSON to {filepath}")
        return filepath

    def export_m3u(self, filename: str = "AniXLinks.m3u") -> str:
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            f.write(f'#EXTINF:-1,AniXLinks - Generated by {self.author_info["name"]} (@{self.author_info["instagram"]})\n')
            f.write(f'#EXTVLCOPT:http-user-agent=AniXLinks/{self.author_info["version"]}\n')
            f.write('\n')
            
            for group, channels in sorted(self.channels.items()):
                for channel in channels:
                    extinf = f'#EXTINF:-1 tvg-id="{channel.get("tvg_id", "")}" tvg-logo="{channel["logo"]}" group-title="{group}",{channel["name"]}'
                    f.write(f'{extinf}\n')
                    f.write(f'{channel["url"]}\n')
        
        logging.info(f"[✓] Exported M3U to {filepath}")
        return filepath

    def export_stats(self, filename: str = "stats.json") -> str:
        filepath = os.path.join(self.output_dir, filename)
        
        stats = {
            "generated_at": datetime.now(pytz.timezone('Asia/Kolkata')).isoformat(),
            "total_channels": sum(len(channels) for channels in self.channels.values()),
            "total_groups": len(self.channels),
            "groups_breakdown": {
                group: len(channels) for group, channels in self.channels.items()
            },
            "author": self.author_info,
            "active_channels": sum(
                1 for channels in self.channels.values() 
                for channel in channels 
                if channel.get("status") == "active"
            ) if self.check_links else "not_checked"
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        
        logging.info(f"[✓] Exported stats to {filepath}")
        return filepath

def get_premium_sources() -> List[str]:
    return [
        "https://raw.githubusercontent.com/sydul104/main04/refs/heads/main/my",
        "https://raw.githubusercontent.com/Miraz6755/Bdixtv/refs/heads/main/Livetv.m3u8",
        "https://raw.githubusercontent.com/Yeadee/Toffee/refs/heads/main/toffee_ns_player.m3u",
        "https://raw.githubusercontent.com/MohammadJoyChy/BDIXTV/refs/heads/main/Aynaott",
        "https://raw.githubusercontent.com/skjahangirkabir/Bdix-549.m3u/refs/heads/main/BDIX-549.m3u8",
        "https://raw.githubusercontent.com/Arunjunan20/My-IPTV/refs/heads/main/index.html",
        "https://raw.githubusercontent.com/AHIL44444/GAZI-LIVE-TV-M3U8/refs/heads/main/index.html",
        "https://aynaxpranto.vercel.app/files/playlist.m3u",
        "https://raw.githubusercontent.com/tanvir907/bdix/refs/heads/main/bdix.m3u",
        "https://raw.githubusercontent.com/shuvo880/iptv/refs/heads/master/MiME%20(SHUVO)",
        "https://raw.githubusercontent.com/Shaharum1010/SmartFlix_Tv_Web/refs/heads/main/SmartFlixtv",
        "https://raw.githubusercontent.com/mr-masudrana/LiveTV/refs/heads/main/Bangla_Playlist.m3u",
        "https://raw.githubusercontent.com/mr-masudrana/Web_Player-IPTV/refs/heads/main/channels.json",
        "https://iptv-org.github.io/iptv/countries/bd.m3u",
        "https://raw.githubusercontent.com/FreeIPTV/Countries/master/BD_Bangladesh.m3u",
        "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist/BD.m3u8",
    ]

def main():
    print("[+] AniXLinks - Advanced Mix M3U Collector")
    print("=" * 50)
    
    sources = get_premium_sources()
    
    with AniXLinksCollector(
        country="Bangladesh", 
        check_links=os.getenv('SKIP_LINK_CHECK', 'false').lower() != 'true'
    ) as collector:
        
        collector.process_sources(sources)
        
        collector.export_anixlinks_json("AniXLinks.json")
        collector.export_m3u("AniXLinks.m3u")
        collector.export_stats("stats.json")
        
        total_channels = sum(len(ch) for ch in collector.channels.values())
        total_groups = len(collector.channels)
        
        print(f"\n[✓] Collection Complete!")
        print(f"[*] Total Channels: {total_channels}")
        print(f"[*] Total Groups: {total_groups}")
        print(f"[*] Output Directory: {collector.output_dir}")
        print(f"[*] Generated: {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S IST')}")
        
        if total_channels == 0:
            print("[!] No channels collected. Check your internet connection and source URLs.")
            sys.exit(1)
        else:
            print(f"[+] Successfully collected {total_channels} channels!")

if __name__ == "__main__":
    main()