# mock_swiggy.py
import re

MENU = {
    "paneer tikka": 250,
    "garlic naan": 60,
    "butter chicken": 350,
    "dal makhani": 220,
    "jeera rice": 120,
    "biryani": 300,
    "coke": 50,
    "thumbs up": 50
}

class MockSwiggyMCP:
    def __init__(self):
        self.cart = []
        
    def extract_items_from_text(self, text):
        text = text.lower()
        items_found = []
        for item in MENU.keys():
            if item in text:
                items_found.append(item)
        return items_found

    def process_order(self, text):
        """
        Parses the text and adds items to the mock cart.
        Returns a confirmation message.
        """
        items_to_add = self.extract_items_from_text(text)
        
        if not items_to_add:
            return "I couldn't find any items on our menu from your request. We have: Paneer Tikka, Garlic Naan, Butter Chicken, Dal Makhani, Jeera Rice, Biryani, Coke, and Thumbs Up."
        
        total_price = 0
        added_items_msg = []
        
        for item in items_to_add:
            price = MENU[item]
            self.cart.append({"name": item, "price": price})
            total_price += price
            added_items_msg.append(f"{item.title()} (₹{price})")
            
        items_str = ", ".join(added_items_msg)
        return f"Success! I have added {items_str} to your Swiggy cart. Your total is ₹{total_price}. Please confirm to place the order."