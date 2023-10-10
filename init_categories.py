from app import app, db, Category

def init_categories():
    categories_list = ["Groceries", "Entertainment", "Rent", "Utilities", "Dining Out"]

    for cat_name in categories_list:
        # Check if the category already exists
        existing_category = Category.query.filter_by(name=cat_name).first()
        if not existing_category:
            category = Category(name=cat_name)
            db.session.add(category)

    db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        init_categories()
