import json
import logging
from datetime import datetime

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import config
from utils import (
    load_catalog,
    save_catalog,
    load_orders,
    save_order,
    generate_order_id,
    calculate_total,
    format_order_notification,
    format_catalog_list,
    get_category,
    get_product,
    add_product,
    edit_product,
    remove_product,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

END = ConversationHandler.END

# ── Conversation states ────────────────────────────────────────────────────────
(
    AGE_GATE,
    MAIN_MENU,
    BROWSE_CAT,
    BROWSE_PROD,
    PROD_DETAIL,
    CART,
    CHECKOUT_NAME,
    CHECKOUT_PHONE,
    CHECKOUT_DELIVERY_TYPE,
    CHECKOUT_ADDRESS,
    CHECKOUT_PAYMENT,
    AWAIT_SCREENSHOT,
    ADMIN_ADD_CAT,
    ADMIN_ADD_NAME,
    ADMIN_ADD_DESC,
    ADMIN_ADD_PRICE,
    ADMIN_EDIT_SELECT,
    ADMIN_EDIT_FIELD,
    ADMIN_EDIT_VALUE,
    ADMIN_REMOVE_SELECT,
    ADMIN_REMOVE_CONFIRM,
    ADMIN_IMG_SELECT,
    ADMIN_IMG_UPLOAD,
) = range(23)


# ── Shared helpers ─────────────────────────────────────────────────────────────

def is_admin(update: Update) -> bool:
    return update.effective_chat.id == config.ADMIN_CHAT_ID


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 Browse Shop", callback_data="menu_browse")],
        [InlineKeyboardButton("🛒 My Cart", callback_data="menu_cart")],
        [InlineKeyboardButton("ℹ️ Info", callback_data="menu_info")],
        [InlineKeyboardButton("📞 Contact", callback_data="menu_contact")],
    ])


def _shop_button_keyboard() -> ReplyKeyboardMarkup | None:
    """Persistent reply keyboard with Mini App button. Returns None if WEBAPP_URL not set."""
    if not config.WEBAPP_URL:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🛍 Open Shop", web_app=WebAppInfo(url=config.WEBAPP_URL))]],
        resize_keyboard=True,
    )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send a new main menu message. Used after /start and post-checkout."""
    shop_kb = _shop_button_keyboard()
    if shop_kb and not context.user_data.get("shop_button_shown"):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Tap the button below anytime to open the shop. 👇",
            reply_markup=shop_kb,
        )
        context.user_data["shop_button_shown"] = True
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🏠 {config.SHOP_NAME} — What would you like to do?",
        reply_markup=_main_menu_keyboard(),
    )
    return MAIN_MENU


# ── Age gate ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data.get("age_verified"):
        return await show_main_menu(update, context)
    await update.message.reply_text(
        f"🔞 {config.SHOP_NAME} sells vaping products.\n\n"
        "Please confirm you are 18 years of age or older.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes, I'm 18+", callback_data="age_yes"),
            InlineKeyboardButton("❌ No", callback_data="age_no"),
        ]]),
    )
    return AGE_GATE


async def age_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "age_yes":
        context.user_data["age_verified"] = True
        context.user_data.setdefault("cart", [])
        return await show_main_menu(update, context)
    await query.edit_message_text("Sorry, this shop is for adults only. 🚫")
    return END


# ── Main menu ─────────────────────────────────────────────────────────────────

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Edit current message back to main menu. Used from info/contact/browse/cart."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        f"🏠 {config.SHOP_NAME} — What would you like to do?",
        reply_markup=_main_menu_keyboard(),
    )
    return MAIN_MENU


async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "menu_browse":
        return await show_categories(update, context)
    if query.data == "menu_cart":
        return await show_cart(update, context)
    if query.data == "menu_info":
        await query.edit_message_text(
            f"ℹ️ *{config.SHOP_NAME}*\n\n{config.SHOP_INFO}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back_menu")]]),
            parse_mode="Markdown",
        )
        return MAIN_MENU
    if query.data == "menu_contact":
        await query.edit_message_text(
            f"📞 *Contact*\n\n{config.CONTACT_INFO}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back_menu")]]),
            parse_mode="Markdown",
        )
        return MAIN_MENU
    return MAIN_MENU


# ── Browse ────────────────────────────────────────────────────────────────────

async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    catalog = load_catalog(config.CATALOG_PATH)
    keyboard = [
        [InlineKeyboardButton(cat["name"], callback_data=f"cat_{cat['id']}")]
        for cat in catalog["categories"]
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_menu")])
    text = "🛍 Choose a category:"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return BROWSE_CAT


async def _render_products(update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: str) -> int:
    catalog = load_catalog(config.CATALOG_PATH)
    cat = get_category(catalog, category_id)
    available = [p for p in cat["products"] if p["available"]]
    if not available:
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_cat")]]
        text = f"{cat['name']}\n\nNo products available yet."
    else:
        keyboard = [
            [InlineKeyboardButton(f"{p['name']} — €{p['price']:.2f}", callback_data=f"prod_{p['id']}")]
            for p in available
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back_cat")])
        text = f"{cat['name']}"
    # If returning from a photo-based product detail, the current message is a photo.
    # We must delete it and send a fresh text message instead of editing.
    if context.user_data.pop("in_photo_detail", False):
        await update.callback_query.message.delete()
        await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return BROWSE_PROD


async def browse_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    category_id = query.data[4:]  # strip "cat_"
    context.user_data["current_category"] = category_id
    return await _render_products(update, context, category_id)


async def back_to_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    return await show_categories(update, context)


async def back_to_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    return await _render_products(update, context, context.user_data["current_category"])


async def _render_product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: str) -> int:
    catalog = load_catalog(config.CATALOG_PATH)
    product = get_product(catalog, context.user_data["current_category"], product_id)
    keyboard = [
        [InlineKeyboardButton("🛒 Add to Cart", callback_data=f"addcart_{product_id}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_prod")],
    ]
    caption = f"*{product['name']}*\n\n{product['description']}\n\n💶 €{product['price']:.2f}"
    image = product.get("image")
    if image:
        # Replace the current message with a photo+caption message.
        await update.callback_query.message.delete()
        await update.callback_query.message.reply_photo(
            photo=image,
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        context.user_data["in_photo_detail"] = True
    else:
        await update.callback_query.edit_message_text(
            caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        context.user_data["in_photo_detail"] = False
    return PROD_DETAIL


async def show_product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    product_id = query.data[5:]  # strip "prod_"
    context.user_data["current_product"] = product_id
    return await _render_product_detail(update, context, product_id)


async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Added to cart! ✅")
    product_id = query.data[8:]  # strip "addcart_"
    catalog = load_catalog(config.CATALOG_PATH)
    product = get_product(catalog, context.user_data["current_category"], product_id)
    cart = context.user_data.setdefault("cart", [])
    for item in cart:
        if item["id"] == product_id:
            item["qty"] += 1
            return await _render_product_detail(update, context, product_id)
    cart.append({
        "id": product_id,
        "category_id": context.user_data["current_category"],
        "name": product["name"],
        "qty": 1,
        "price": product["price"],
    })
    return await _render_product_detail(update, context, product_id)


# ── Cart ──────────────────────────────────────────────────────────────────────

async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cart = context.user_data.get("cart", [])
    if not cart:
        keyboard = [
            [InlineKeyboardButton("🛍 Browse Shop", callback_data="menu_browse")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_menu")],
        ]
        text = "🛒 Your cart is empty."
    else:
        total = calculate_total(cart)
        lines = [
            f"• {item['name']} x{item['qty']} — €{item['price'] * item['qty']:.2f}"
            for item in cart
        ]
        text = "🛒 *Your Cart*\n\n" + "\n".join(lines) + f"\n\n*Total: €{total:.2f}*"
        keyboard = [
            [InlineKeyboardButton("✅ Checkout", callback_data="checkout")],
            [InlineKeyboardButton("🗑 Clear Cart", callback_data="clearcart")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_menu")],
        ]
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
        )
    return CART


async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Cart cleared.")
    context.user_data["cart"] = []
    return await show_cart(update, context)


# ── Checkout ──────────────────────────────────────────────────────────────────

async def checkout_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["checkout"] = {}
    await query.edit_message_text("📋 Let's complete your order.\n\nWhat's your full name?")
    return CHECKOUT_NAME


async def collect_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["checkout"]["name"] = update.message.text.strip()
    await update.message.reply_text("📱 What's your phone number?")
    return CHECKOUT_PHONE


async def collect_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["checkout"]["phone"] = update.message.text.strip()
    await update.message.reply_text(
        "How would you like to receive your order?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🚚 Delivery", callback_data="delivery_delivery"),
            InlineKeyboardButton("🏪 Pickup", callback_data="delivery_pickup"),
        ]]),
    )
    return CHECKOUT_DELIVERY_TYPE


async def _ask_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("💵 In-Person / Cash", callback_data="payment_inperson"),
        InlineKeyboardButton("💳 PayPal", callback_data="payment_paypal"),
    ]])
    text = "💳 How would you like to pay?"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)
    return CHECKOUT_PAYMENT


async def collect_delivery_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    delivery_type = query.data.split("_", 1)[1]  # "delivery" or "pickup"
    context.user_data["checkout"]["delivery_type"] = delivery_type
    if delivery_type == "delivery":
        await query.edit_message_text("📍 What's your delivery address?")
        return CHECKOUT_ADDRESS
    context.user_data["checkout"]["address"] = ""
    return await _ask_payment(update, context)


async def collect_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["checkout"]["address"] = update.message.text.strip()
    return await _ask_payment(update, context)


async def collect_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    payment = query.data.split("_", 1)[1]  # "inperson" or "paypal"
    checkout = context.user_data["checkout"]
    checkout["payment"] = payment

    cart = context.user_data["cart"]
    order_id = generate_order_id(config.ORDERS_PATH)
    order = {
        "id": order_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "customer": {"name": checkout["name"], "phone": checkout["phone"]},
        "delivery": {"type": checkout["delivery_type"], "address": checkout.get("address", "")},
        "items": cart,
        "total": calculate_total(cart),
        "payment": payment,
        "status": "pending",
    }
    save_order(order, config.ORDERS_PATH)
    context.user_data["cart"] = []
    context.user_data["current_order_id"] = order_id

    # Notify admin
    await context.bot.send_message(
        chat_id=config.ADMIN_CHAT_ID,
        text=format_order_notification(order, config.SHOP_NAME),
    )

    if payment == "paypal":
        await query.edit_message_text(
            f"✅ Order #{order_id} received!\n\n"
            f"💳 Please pay via PayPal:\n{config.PAYPAL_LINK}\n\n"
            "Once paid, send a screenshot of your confirmation here."
        )
        return AWAIT_SCREENSHOT

    await query.edit_message_text(
        f"✅ Order #{order_id} received!\n\n"
        "We'll contact you shortly to arrange everything. 🙌"
    )
    return await show_main_menu(update, context)


# ── PayPal screenshot ─────────────────────────────────────────────────────────

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    order_id = context.user_data.get("current_order_id", "?")
    user = update.effective_user
    caption = (
        f"📸 Payment confirmation for order #{order_id}\n"
        f"From: {user.full_name} (@{user.username or 'no username'})"
    )
    if update.message.photo:
        await context.bot.send_photo(
            chat_id=config.ADMIN_CHAT_ID,
            photo=update.message.photo[-1].file_id,
            caption=caption,
        )
    else:
        await context.bot.send_document(
            chat_id=config.ADMIN_CHAT_ID,
            document=update.message.document.file_id,
            caption=caption,
        )
    await update.message.reply_text(
        "Thanks! Payment confirmation received. We'll contact you shortly. ✅"
    )
    return await show_main_menu(update, context)


async def remind_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Please send a screenshot of your PayPal payment confirmation. 📸"
    )
    return AWAIT_SCREENSHOT


# ── Mini App order handler ────────────────────────────────────────────────────

async def handle_webapp_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Receives a completed order submitted from the Mini App via sendData()."""
    raw = update.effective_message.web_app_data.data
    try:
        order_data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        await update.message.reply_text("Sorry, something went wrong with your order. Please try again.")
        return

    order_id = generate_order_id(config.ORDERS_PATH)
    order = {
        "id": order_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "customer": {
            "name": order_data.get("name", ""),
            "phone": order_data.get("phone", ""),
        },
        "delivery": {
            "type": order_data.get("delivery_type", "pickup"),
            "address": order_data.get("address", ""),
        },
        "items": order_data.get("items", []),
        "total": calculate_total(order_data.get("items", [])),
        "payment": order_data.get("payment", "inperson"),
        "status": "pending",
    }
    save_order(order, config.ORDERS_PATH)

    await context.bot.send_message(
        chat_id=config.ADMIN_CHAT_ID,
        text=format_order_notification(order, config.SHOP_NAME),
    )

    payment = order["payment"]
    if payment == "paypal":
        await update.message.reply_text(
            f"✅ Order #{order_id} received!\n\n"
            f"💳 Please pay via PayPal:\n{config.PAYPAL_LINK}\n\n"
            "Once paid, send a screenshot of your confirmation here."
        )
        context.user_data["current_order_id"] = order_id
    else:
        await update.message.reply_text(
            f"✅ Order #{order_id} received!\n\n"
            "We'll contact you shortly to arrange everything. 🙌"
        )


# ── Admin helpers ─────────────────────────────────────────────────────────────

def _all_products(catalog: dict) -> list:
    """Return list of (category_id, product) tuples for all products."""
    result = []
    for cat in catalog["categories"]:
        for p in cat["products"]:
            result.append((cat["id"], p))
    return result


# ── Admin read commands ───────────────────────────────────────────────────────

async def cmd_list_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    catalog = load_catalog(config.CATALOG_PATH)
    await update.message.reply_text(
        "📦 *Product Catalog*\n" + format_catalog_list(catalog),
        parse_mode="Markdown",
    )


async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    orders = load_orders(config.ORDERS_PATH)
    if not orders:
        await update.message.reply_text("No orders yet.")
        return
    recent = list(reversed(orders[-10:]))
    lines = []
    for o in recent:
        icon = "✅" if o["status"] == "paid" else "⏳"
        lines.append(f"{icon} #{o['id']} — {o['customer']['name']} — €{o['total']:.2f} ({o['payment']})")
    await update.message.reply_text(
        "📋 *Last 10 Orders*\n\n" + "\n".join(lines), parse_mode="Markdown"
    )


async def cmd_paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /paid <order_id>")
        return
    order_id = context.args[0]
    orders = load_orders(config.ORDERS_PATH)
    for o in orders:
        if o["id"] == order_id:
            o["status"] = "paid"
            with open(config.ORDERS_PATH, "w", encoding="utf-8") as f:
                json.dump(orders, f, indent=2, ensure_ascii=False)
            await update.message.reply_text(f"✅ Order #{order_id} marked as paid.")
            return
    await update.message.reply_text(f"Order #{order_id} not found.")


# ── Admin: /addproduct ────────────────────────────────────────────────────────

async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update):
        return END
    catalog = load_catalog(config.CATALOG_PATH)
    keyboard = [
        [InlineKeyboardButton(cat["name"], callback_data=f"addcat_{cat['id']}")]
        for cat in catalog["categories"]
    ]
    await update.message.reply_text("Which category?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_ADD_CAT


async def admin_add_pick_cat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["admin_add_category"] = query.data[7:]  # strip "addcat_"
    await query.edit_message_text("Product name?")
    return ADMIN_ADD_NAME


async def admin_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["admin_add_name"] = update.message.text.strip()
    await update.message.reply_text("Description?")
    return ADMIN_ADD_DESC


async def admin_add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["admin_add_desc"] = update.message.text.strip()
    await update.message.reply_text("Price (e.g. 15.90)?")
    return ADMIN_ADD_PRICE


async def admin_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        price = float(update.message.text.strip().replace(",", "."))
    except ValueError:
        await update.message.reply_text("Invalid price. Enter a number like 15.90:")
        return ADMIN_ADD_PRICE
    catalog = load_catalog(config.CATALOG_PATH)
    catalog = add_product(
        catalog,
        context.user_data["admin_add_category"],
        context.user_data["admin_add_name"],
        context.user_data["admin_add_desc"],
        price,
    )
    save_catalog(catalog, config.CATALOG_PATH)
    name = context.user_data["admin_add_name"]
    await update.message.reply_text(f"✅ '{name}' added to catalog.")
    return END


# ── Admin: /removeproduct ─────────────────────────────────────────────────────

async def admin_remove_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update):
        return END
    catalog = load_catalog(config.CATALOG_PATH)
    products = _all_products(catalog)
    if not products:
        await update.message.reply_text("No products to remove.")
        return END
    keyboard = [
        [InlineKeyboardButton(
            f"{p['name']} (€{p['price']:.2f})",
            callback_data=f"rm_{cat_id}__{p['id']}"
        )]
        for cat_id, p in products
    ]
    await update.message.reply_text("Which product to remove?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_REMOVE_SELECT


async def admin_remove_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, rest = query.data.split("rm_", 1)
    cat_id, product_id = rest.split("__", 1)
    context.user_data["admin_rm_cat"] = cat_id
    context.user_data["admin_rm_prod"] = product_id
    catalog = load_catalog(config.CATALOG_PATH)
    product = get_product(catalog, cat_id, product_id)
    await query.edit_message_text(
        f"Remove *{product['name']}*?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Yes, remove", callback_data="rm_confirm_yes"),
            InlineKeyboardButton("❌ Cancel", callback_data="rm_confirm_no"),
        ]]),
        parse_mode="Markdown",
    )
    return ADMIN_REMOVE_CONFIRM


async def admin_remove_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "rm_confirm_yes":
        catalog = load_catalog(config.CATALOG_PATH)
        catalog = remove_product(catalog, context.user_data["admin_rm_cat"], context.user_data["admin_rm_prod"])
        save_catalog(catalog, config.CATALOG_PATH)
        await query.edit_message_text("✅ Product removed.")
    else:
        await query.edit_message_text("Cancelled.")
    return END


# ── Admin: /editproduct ───────────────────────────────────────────────────────

async def admin_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update):
        return END
    catalog = load_catalog(config.CATALOG_PATH)
    products = _all_products(catalog)
    if not products:
        await update.message.reply_text("No products to edit.")
        return END
    keyboard = [
        [InlineKeyboardButton(p["name"], callback_data=f"ed_{cat_id}__{p['id']}")]
        for cat_id, p in products
    ]
    await update.message.reply_text("Which product to edit?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_EDIT_SELECT


async def admin_edit_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, rest = query.data.split("ed_", 1)
    cat_id, product_id = rest.split("__", 1)
    context.user_data["admin_ed_cat"] = cat_id
    context.user_data["admin_ed_prod"] = product_id
    await query.edit_message_text(
        "Which field to edit?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Name", callback_data="edfield_name")],
            [InlineKeyboardButton("Description", callback_data="edfield_description")],
            [InlineKeyboardButton("Price", callback_data="edfield_price")],
            [InlineKeyboardButton("Available (true/false)", callback_data="edfield_available")],
        ]),
    )
    return ADMIN_EDIT_FIELD


async def admin_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    field = query.data[8:]  # strip "edfield_"
    context.user_data["admin_ed_field"] = field
    await query.edit_message_text(f"Enter new value for *{field}*:", parse_mode="Markdown")
    return ADMIN_EDIT_VALUE


async def admin_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    field = context.user_data["admin_ed_field"]
    if field == "price":
        try:
            value = float(raw.replace(",", "."))
        except ValueError:
            await update.message.reply_text("Invalid price. Enter a number (e.g. 12.50):")
            return ADMIN_EDIT_VALUE
    elif field == "available":
        if raw.lower() in ("true", "yes", "1"):
            value = True
        elif raw.lower() in ("false", "no", "0"):
            value = False
        else:
            await update.message.reply_text("Enter true or false:")
            return ADMIN_EDIT_VALUE
    else:
        value = raw
    catalog = load_catalog(config.CATALOG_PATH)
    catalog = edit_product(catalog, context.user_data["admin_ed_cat"], context.user_data["admin_ed_prod"], field, value)
    save_catalog(catalog, config.CATALOG_PATH)
    await update.message.reply_text(f"✅ {field} updated.")
    return END


# ── Admin: /setproductimage ───────────────────────────────────────────────────

async def admin_img_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update):
        return END
    catalog = load_catalog(config.CATALOG_PATH)
    products = _all_products(catalog)
    if not products:
        await update.message.reply_text("No products in catalog.")
        return END
    keyboard = [
        [InlineKeyboardButton(p["name"], callback_data=f"img_{cat_id}__{p['id']}")]
        for cat_id, p in products
    ]
    await update.message.reply_text("Which product to set image for?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_IMG_SELECT


async def admin_img_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, rest = query.data.split("img_", 1)
    cat_id, product_id = rest.split("__", 1)
    context.user_data["admin_img_cat"] = cat_id
    context.user_data["admin_img_prod"] = product_id
    await query.edit_message_text("Send me a photo to use for this product:")
    return ADMIN_IMG_UPLOAD


async def admin_img_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.photo:
        await update.message.reply_text("Please send a photo image.")
        return ADMIN_IMG_UPLOAD
    file_id = update.message.photo[-1].file_id
    catalog = load_catalog(config.CATALOG_PATH)
    catalog = edit_product(
        catalog,
        context.user_data["admin_img_cat"],
        context.user_data["admin_img_prod"],
        "image",
        file_id,
    )
    save_catalog(catalog, config.CATALOG_PATH)
    await update.message.reply_text("✅ Product image saved.")
    return END


# ── Application wiring ────────────────────────────────────────────────────────

def main() -> None:
    app = Application.builder().token(config.BOT_TOKEN).build()

    customer_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AGE_GATE: [CallbackQueryHandler(age_response, pattern="^age_(yes|no)$")],
            MAIN_MENU: [
                CallbackQueryHandler(main_menu_handler, pattern="^menu_"),
                CallbackQueryHandler(back_to_menu, pattern="^back_menu$"),
                CallbackQueryHandler(show_cart, pattern="^menu_cart$"),
            ],
            BROWSE_CAT: [
                CallbackQueryHandler(browse_products, pattern="^cat_"),
                CallbackQueryHandler(back_to_menu, pattern="^back_menu$"),
            ],
            BROWSE_PROD: [
                CallbackQueryHandler(show_product_detail, pattern="^prod_"),
                CallbackQueryHandler(back_to_categories, pattern="^back_cat$"),
            ],
            PROD_DETAIL: [
                CallbackQueryHandler(add_to_cart, pattern="^addcart_"),
                CallbackQueryHandler(back_to_products, pattern="^back_prod$"),
            ],
            CART: [
                CallbackQueryHandler(checkout_start, pattern="^checkout$"),
                CallbackQueryHandler(clear_cart, pattern="^clearcart$"),
                CallbackQueryHandler(back_to_menu, pattern="^back_menu$"),
                CallbackQueryHandler(show_categories, pattern="^menu_browse$"),
            ],
            CHECKOUT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_name)],
            CHECKOUT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_phone)],
            CHECKOUT_DELIVERY_TYPE: [CallbackQueryHandler(collect_delivery_type, pattern="^delivery_")],
            CHECKOUT_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, collect_address)],
            CHECKOUT_PAYMENT: [CallbackQueryHandler(collect_payment, pattern="^payment_")],
            AWAIT_SCREENSHOT: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, handle_screenshot),
                MessageHandler(filters.TEXT & ~filters.COMMAND, remind_screenshot),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=False,
    )

    add_conv = ConversationHandler(
        entry_points=[CommandHandler("addproduct", admin_add_start)],
        states={
            ADMIN_ADD_CAT: [CallbackQueryHandler(admin_add_pick_cat, pattern="^addcat_")],
            ADMIN_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_name)],
            ADMIN_ADD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_desc)],
            ADMIN_ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_price)],
        },
        fallbacks=[],
    )

    remove_conv = ConversationHandler(
        entry_points=[CommandHandler("removeproduct", admin_remove_start)],
        states={
            ADMIN_REMOVE_SELECT: [CallbackQueryHandler(admin_remove_select, pattern="^rm_[^c]")],
            ADMIN_REMOVE_CONFIRM: [CallbackQueryHandler(admin_remove_confirm, pattern="^rm_confirm_")],
        },
        fallbacks=[],
    )

    edit_conv = ConversationHandler(
        entry_points=[CommandHandler("editproduct", admin_edit_start)],
        states={
            ADMIN_EDIT_SELECT: [CallbackQueryHandler(admin_edit_select, pattern="^ed_")],
            ADMIN_EDIT_FIELD: [CallbackQueryHandler(admin_edit_field, pattern="^edfield_")],
            ADMIN_EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit_value)],
        },
        fallbacks=[],
    )

    img_conv = ConversationHandler(
        entry_points=[CommandHandler("setproductimage", admin_img_start)],
        states={
            ADMIN_IMG_SELECT: [CallbackQueryHandler(admin_img_select, pattern="^img_")],
            ADMIN_IMG_UPLOAD: [MessageHandler(filters.PHOTO, admin_img_upload)],
        },
        fallbacks=[],
    )

    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_order))
    app.add_handler(customer_conv)
    app.add_handler(add_conv)
    app.add_handler(remove_conv)
    app.add_handler(edit_conv)
    app.add_handler(img_conv)
    app.add_handler(CommandHandler("listproducts", cmd_list_products))
    app.add_handler(CommandHandler("orders", cmd_orders))
    app.add_handler(CommandHandler("paid", cmd_paid))

    logger.info("Bot started. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
