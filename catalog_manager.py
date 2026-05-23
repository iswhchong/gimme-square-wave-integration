import json
import os

class CatalogManager:
    def __init__(self, catalog_file="square_catalog_full.json"):
        self.item_category_map = {} # ItemID -> CategoryName
        self.load_catalog(catalog_file)

    def load_catalog(self, catalog_file):
        if not os.path.exists(catalog_file):
            print(f"Warning: Catalog file {catalog_file} not found. Item mapping will fail.")
            return

        with open(catalog_file, 'r') as f:
            data = json.load(f)
        
        objects = data.get('objects', [])
        
        # First pass: map Category IDs to Names
        cat_id_to_name = {}
        for obj in objects:
            if obj['type'] == 'CATEGORY':
                cat_id_to_name[obj['id']] = obj['category_data']['name']
        
        # Second pass: map Item IDs to Category Names
        for obj in objects:
            if obj['type'] == 'ITEM':
                item_id = obj['id']
                # Item has 'category_id'
                # Item has 'category_id' (legacy) or 'categories' (list) or 'reporting_category'
                item_data = obj['item_data']
                cat_id = item_data.get('category_id')
                
                # Check reporting_category
                if not cat_id:
                     rep_cat = item_data.get('reporting_category')
                     if rep_cat:
                         cat_id = rep_cat.get('id')
                         
                # Check categories list (take first)
                if not cat_id:
                    cats = item_data.get('categories')
                    if cats and len(cats) > 0:
                        cat_id = cats[0].get('id')

                if cat_id and cat_id in cat_id_to_name:
                    self.item_category_map[item_id] = cat_id_to_name[cat_id]
                    # Also map variation IDs? usually Order line item points to variation ID (catalog_object_id)
                    # Use 'variations' list
                    for var in obj['item_data'].get('variations', []):
                        self.item_category_map[var['id']] = cat_id_to_name[cat_id]

    def get_category_for_item(self, item_id):
        return self.item_category_map.get(item_id, "Uncategorized")
