import requests
import time
from utils.db import upsert_tags

class DanbooruScraper:
    def __init__(self):
        self.base_url = "https://danbooru.donmai.us/tags.json"
        self.headers = {
            "User-Agent": "AIContentCreator/1.0 (puert@example.com)" 
        }
        # Mapping Danbooru categories to our categories
        # 0: General -> General (New)
        # 1: Artist -> Artist (New)
        # 3: Copyright -> Copyright
        # 4: Character -> Character
        # 5: Meta -> Quality Tag (Best fit)
        self.category_map = {
            0: "General",
            1: "Artist",
            3: "Copyright",
            4: "Character",
            5: "Quality Tag"
        }

    def fetch_tags(self, limit=1000, page=1, order="count"):
        """
        Fetch tags from Danbooru API.
        """
        params = {
            "limit": limit,
            "page": page,
            "search[order]": order
        }
        
        try:
            print(f"Fetching page {page}...")
            response = requests.get(self.base_url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching tags: {e}")
            return []

    def process_tags(self, raw_tags):
        """
        Process raw tags and map them to our DB schema.
        """
        processed_tags = []
        for tag in raw_tags:
            # Skip if post_count is 0 (shouldn't happen with default order but good to check)
            if tag.get('post_count', 0) == 0:
                continue
                
            category_id = tag.get('category', 0)
            category_name = self.category_map.get(category_id, "General")
            
            # Special handling for some General tags to map to our specific UI categories
            # This is a heuristic mapping since Danbooru puts everything in General
            name = tag.get('name', '')
            
            # Simple heuristics for UI categories based on keywords
            if category_name == "General":
                if any(x in name for x in ['hair', 'eyes', 'skin', 'breasts', 'wings', 'ears', 'tail']):
                    category_name = "Character Appearance"
                elif any(x in name for x in ['dress', 'shirt', 'skirt', 'uniform', 'gloves', 'hat', 'shoes', 'bikini']):
                    category_name = "Clothing"
                elif any(x in name for x in ['sitting', 'standing', 'lying', 'looking', 'smile', 'blush', 'tears']):
                    category_name = "Expression & Action"
                elif any(x in name for x in ['view', 'perspective', 'close-up', 'full_body', 'from_']):
                    category_name = "Camera / Positioning"
                elif any(x in name for x in ['light', 'shadow', 'blur', 'bokeh', 'dark']):
                    category_name = "Lighting & Effects"
                elif any(x in name for x in ['indoors', 'outdoors', 'sky', 'cloud', 'room', 'tree', 'flower', 'water']):
                    category_name = "Scene Atmosphere"

            processed_tags.append({
                'name': name,
                'category': category_name,
                'post_count': tag.get('post_count', 0)
            })
            
        return processed_tags

    def run(self, max_pages=5):
        """
        Run the scraper for a specified number of pages.
        """
        total_imported = 0
        for page in range(1, max_pages + 1):
            raw_tags = self.fetch_tags(page=page)
            if not raw_tags:
                break
                
            processed_tags = self.process_tags(raw_tags)
            count = upsert_tags(processed_tags)
            total_imported += count
            print(f"Page {page}: Processed {len(processed_tags)} tags, Upserted {count} tags.")
            
            # Be nice to the API
            time.sleep(1)
            
        print(f"Scraping completed. Total tags upserted: {total_imported}")

if __name__ == "__main__":
    scraper = DanbooruScraper()
    scraper.run(max_pages=10) # Scrape top 10,000 tags
