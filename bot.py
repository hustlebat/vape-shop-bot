import json
import logging
from datetime import datetime

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
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
    add_product_from_json,
    edit_product,
    remove_product,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

END = ConversationHandler.END

NUM_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟", "1️⃣1️⃣", "1️⃣2️⃣"]

# ── Conversation states ────────────────────────────────────────────────────────
(
    AGE_GATE,
    MAIN_MENU,
    BROWSE_CAT,
    BROWSE_PROD,
    PROD_DETAIL,
    PROD_MIX_SELECT,
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
    ADMIN_IMPORT_CAT,
    ADMIN_IMPORT_JSON,
) = range(26)


# ── Shared helpers ─────────────────────────────────────────────────────────────

def is_admin(update: Update) -> bool:
    return update.effective_chat.id == config.ADMIN_CHAT_ID


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 Parcourir la boutique", callback_data="menu_browse")],
        [InlineKeyboardButton("🛒 Mon panier", callback_data="menu_cart")],
        [InlineKeyboardButton("ℹ️ Infos", callback_data="menu_info")],
        [InlineKeyboardButton("📞 Contact", callback_data="menu_contact")],
    ])


def _shop_button_keyboard() -> ReplyKeyboardMarkup | None:
    if not config.WEBAPP_URL:
        return None
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🛍 Ouvrir la boutique", web_app=WebAppInfo(url=config.WEBAPP_URL))]],
        resize_keyboard=True,
    )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    shop_kb = _shop_button_keyboard()
    if shop_kb and not context.user_data.get("shop_button_shown"):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Appuyez sur le bouton ci-dessous pour ouvrir la boutique. 👇",
            reply_markup=shop_kb,
        )
        context.user_data["shop_button_shown"] = True
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🏠 {config.SHOP_NAME} — Que souhaitez-vous faire ?",
        reply_markup=_main_menu_keyboard(),
    )
    return MAIN_MENU


# ── Age gate ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.user_data.get("age_verified"):
        return await show_main_menu(update, context)
    await update.message.reply_text(
        f"🔞 {config.SHOP_NAME} vend des produits de vapotage.\n\n"
        "Veuillez confirmer que vous avez 18 ans ou plus.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Oui, j'ai 18+", callback_data="age_yes"),
            InlineKeyboardButton("❌ Non", callback_data="age_no"),
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
    await query.edit_message_text("Désolé, cette boutique est réservée aux adultes. 🚫")
    return END


# ── Main menu ─────────────────────────────────────────────────────────────────

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        f"🏠 {config.SHOP_NAME} — Que souhaitez-vous faire ?",
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
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Retour", callback_data="back_menu")]]),
            parse_mode="Markdown",
        )
        return MAIN_MENU
    if query.data == "menu_contact":
        await query.edit_message_text(
            f"📞 *Contact*\n\n{config.CONTACT_INFO}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Retour", callback_data="back_menu")]]),
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
    keyboard.append([InlineKeyboardButton("⬅️ Retour", callback_data="back_menu")])
    text = "🛍 Choisissez une catégorie :"
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
        keyboard = [[InlineKeyboardButton("⬅️ Retour", callback_data="back_cat")]]
        text = f"{cat['name']}\n\nAucun produit disponible pour l'instant."
    else:
        keyboard = [
            [InlineKeyboardButton(f"{p['name']} — €{p['price']:.2f}", callback_data=f"prod_{p['id']}")]
            for p in available
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Retour", callback_data="back_cat")])
        text = f"{cat['name']}"
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
    mixes = product.get("mixes") or []

    if mixes:
        # Build numbered flavor buttons
        keyboard = [
            [InlineKeyboardButton(
                f"{NUM_EMOJI[i]} {mix['flavors'][0]}",
                callback_data=f"mix_{product_id}_{mix['id']}"
            )]
            for i, mix in enumerate(mixes)
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Retour", callback_data="back_prod")])
        caption = (
            f"*{product['name']}*\n\n"
            f"{product['description']}\n\n"
            f"💶 €{product['price']:.2f}\n\n"
            f"🍬 Sélectionnez votre saveur 👇"
        )
        image = product.get("image")
        if image:
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
        return PROD_MIX_SELECT

    # Standard product (no mixes)
    keyboard = [
        [InlineKeyboardButton("🛒 Ajouter au panier", callback_data=f"addcart_{product_id}")],
        [InlineKeyboardButton("⬅️ Retour", callback_data="back_prod")],
    ]
    caption = f"*{product['name']}*\n\n{product['description']}\n\n💶 €{product['price']:.2f}"
    image = product.get("image")
    if image:
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


async def select_mix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    # callback_data: "mix_{product_id}_{mix_id}"
    _, product_id, mix_id_str = query.data.split("_", 2)
    mix_id = int(mix_id_str)

    catalog = load_catalog(config.CATALOG_PATH)
    product = get_product(catalog, context.user_data["current_category"], product_id)
    mix = next((m for m in product.get("mixes", []) if m["id"] == mix_id), None)

    cart = context.user_data.setdefault("cart", [])
    item_id = f"{product_id}-mix-{mix_id}"
    item_name = f"{product['name']} — Mix #{mix_id}"
    for item in cart:
        if item["id"] == item_id:
            item["qty"] += 1
            await query.answer(f"✅ Mix #{mix_id} ajouté !")
            return PROD_MIX_SELECT
    cart.append({
        "id": item_id,
        "category_id": context.user_data["current_category"],
        "name": item_name,
        "qty": 1,
        "price": product["price"],
    })
    flavors_text = " | ".join(mix["flavors"]) if mix else ""
    await query.answer(f"✅ Mix #{mix_id} ajouté !\n{flavors_text}", show_alert=False)
    return PROD_MIX_SELECT


async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer("Ajouté au panier ! ✅")
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
            [InlineKeyboardButton("🛍 Parcourir la boutique", callback_data="menu_browse")],
            [InlineKeyboardButton("⬅️ Retour", callback_data="back_menu")],
        ]
        text = "🛒 Votre panier est vide."
    else:
        total = calculate_total(cart)
        lines = [
            f"• {item['name']} x{item['qty']} — €{item['price'] * item['qty']:.2f}"
            for item in cart
        ]
        text = "🛒 *Votre panier*\n\n" + "\n".join(lines) + f"\n\n*Total : €{total:.2f}*"
        keyboard = [
            [InlineKeyboardButton("✅ Commander", callback_data="checkout")],
            [InlineKeyboardButton("🗑 Vider le panier", callback_data="clearcart")],
            [InlineKeyboardButton("⬅️ Retour", callback_data="back_menu")],
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
    await query.answer("Panier vidé.")
    context.user_data["cart"] = []
    return await show_cart(update, context)


# ── Checkout ──────────────────────────────────────────────────────────────────

async def checkout_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["checkout"] = {}
    await query.edit_message_text("📋 Finalisons votre commande.\n\nQuel est votre nom complet ?")
    return CHECKOUT_NAME


async def collect_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["checkout"]["name"] = update.message.text.strip()
    await update.message.reply_text("📱 Quel est votre numéro de téléphone ?")
    return CHECKOUT_PHONE


async def collect_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["checkout"]["phone"] = update.message.text.strip()
    await update.message.reply_text(
        "Comment souhaitez-vous recevoir votre commande ?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🚚 Livraison", callback_data="delivery_delivery"),
            InlineKeyboardButton("🏪 Retrait", callback_data="delivery_pickup"),
        ]]),
    )
    return CHECKOUT_DELIVERY_TYPE


async def _ask_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("💵 Espèces", callback_data="payment_inperson"),
        InlineKeyboardButton("💳 PayPal", callback_data="payment_paypal"),
    ]])
    text = "💳 Comment souhaitez-vous payer ?"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)
    return CHECKOUT_PAYMENT


async def collect_delivery_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    delivery_type = query.data.split("_", 1)[1]
    context.user_data["checkout"]["delivery_type"] = delivery_type
    if delivery_type == "delivery":
        await query.edit_message_text("📍 Quelle est votre adresse de livraison ?")
        return CHECKOUT_ADDRESS
    context.user_data["checkout"]["address"] = ""
    return await _ask_payment(update, context)


async def collect_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["checkout"]["address"] = update.message.text.strip()
    return await _ask_payment(update, context)


async def collect_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    payment = query.data.split("_", 1)[1]
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

    await context.bot.send_message(
        chat_id=config.ADMIN_CHAT_ID,
        text=format_order_notification(order, config.SHOP_NAME),
    )

    if payment == "paypal":
        await query.edit_message_text(
            f"✅ Commande #{order_id} reçue !\n\n"
            f"💳 Veuillez payer via PayPal :\n{config.PAYPAL_LINK}\n\n"
            "Une fois le paiement effectué, envoyez une capture d'écran de votre confirmation ici."
        )
        return AWAIT_SCREENSHOT

    await query.edit_message_text(
        f"✅ Commande #{order_id} reçue !\n\n"
        "Nous vous contacterons bientôt pour tout arranger. 🙌"
    )
    return await show_main_menu(update, context)


# ── PayPal screenshot ─────────────────────────────────────────────────────────

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    order_id = context.user_data.get("current_order_id", "?")
    user = update.effective_user
    caption = (
        f"📸 Confirmation de paiement — commande #{order_id}\n"
        f"De : {user.full_name} (@{user.username or 'sans pseudo'})"
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
        "Merci ! Confirmation de paiement reçue. Nous vous contacterons bientôt. ✅"
    )
    return await show_main_menu(update, context)


async def remind_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Veuillez envoyer une capture d'écran de votre confirmation de paiement PayPal. 📸"
    )
    return AWAIT_SCREENSHOT


# ── Mini App order handler ────────────────────────────────────────────────────

async def handle_webapp_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw = update.effective_message.web_app_data.data
    try:
        order_data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        await update.message.reply_text("Une erreur est survenue avec votre commande. Veuillez réessayer.")
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

    if order["payment"] == "paypal":
        await update.message.reply_text(
            f"✅ Commande #{order_id} reçue !\n\n"
            f"💳 Veuillez payer via PayPal :\n{config.PAYPAL_LINK}\n\n"
            "Une fois le paiement effectué, envoyez une capture d'écran ici."
        )
        context.user_data["current_order_id"] = order_id
    else:
        await update.message.reply_text(
            f"✅ Commande #{order_id} reçue !\n\n"
            "Nous vous contacterons bientôt. 🙌"
        )


# ── Admin helpers ─────────────────────────────────────────────────────────────

def _all_products(catalog: dict) -> list:
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
        "📦 *Catalogue produits*\n" + format_catalog_list(catalog),
        parse_mode="Markdown",
    )


async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    orders = load_orders(config.ORDERS_PATH)
    if not orders:
        await update.message.reply_text("Aucune commande pour l'instant.")
        return
    recent = list(reversed(orders[-10:]))
    lines = []
    for o in recent:
        icon = "✅" if o["status"] == "paid" else "⏳"
        lines.append(f"{icon} #{o['id']} — {o['customer']['name']} — €{o['total']:.2f} ({o['payment']})")
    await update.message.reply_text(
        "📋 *10 dernières commandes*\n\n" + "\n".join(lines), parse_mode="Markdown"
    )


async def cmd_paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Utilisation : /paid <order_id>")
        return
    order_id = context.args[0]
    orders = load_orders(config.ORDERS_PATH)
    for o in orders:
        if o["id"] == order_id:
            o["status"] = "paid"
            with open(config.ORDERS_PATH, "w", encoding="utf-8") as f:
                json.dump(orders, f, indent=2, ensure_ascii=False)
            await update.message.reply_text(f"✅ Commande #{order_id} marquée comme payée.")
            return
    await update.message.reply_text(f"Commande #{order_id} introuvable.")


# ── Admin: /addproduct ────────────────────────────────────────────────────────

async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update):
        return END
    catalog = load_catalog(config.CATALOG_PATH)
    keyboard = [
        [InlineKeyboardButton(cat["name"], callback_data=f"addcat_{cat['id']}")]
        for cat in catalog["categories"]
    ]
    await update.message.reply_text("Quelle catégorie ?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_ADD_CAT


async def admin_add_pick_cat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["admin_add_category"] = query.data[7:]
    await query.edit_message_text("Nom du produit ?")
    return ADMIN_ADD_NAME


async def admin_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["admin_add_name"] = update.message.text.strip()
    await update.message.reply_text("Description ?")
    return ADMIN_ADD_DESC


async def admin_add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["admin_add_desc"] = update.message.text.strip()
    await update.message.reply_text("Prix (ex. 15.90) ?")
    return ADMIN_ADD_PRICE


async def admin_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        price = float(update.message.text.strip().replace(",", "."))
    except ValueError:
        await update.message.reply_text("Prix invalide. Entrez un nombre comme 15.90 :")
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
    await update.message.reply_text(f"✅ « {name} » ajouté au catalogue.")
    return END


# ── Admin: /removeproduct ─────────────────────────────────────────────────────

async def admin_remove_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update):
        return END
    catalog = load_catalog(config.CATALOG_PATH)
    products = _all_products(catalog)
    if not products:
        await update.message.reply_text("Aucun produit à supprimer.")
        return END
    keyboard = [
        [InlineKeyboardButton(
            f"{p['name']} (€{p['price']:.2f})",
            callback_data=f"rm_{cat_id}__{p['id']}"
        )]
        for cat_id, p in products
    ]
    await update.message.reply_text("Quel produit supprimer ?", reply_markup=InlineKeyboardMarkup(keyboard))
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
        f"Supprimer *{product['name']}* ?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Oui, supprimer", callback_data="rm_confirm_yes"),
            InlineKeyboardButton("❌ Annuler", callback_data="rm_confirm_no"),
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
        await query.edit_message_text("✅ Produit supprimé.")
    else:
        await query.edit_message_text("Annulé.")
    return END


# ── Admin: /editproduct ───────────────────────────────────────────────────────

async def admin_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update):
        return END
    catalog = load_catalog(config.CATALOG_PATH)
    products = _all_products(catalog)
    if not products:
        await update.message.reply_text("Aucun produit à modifier.")
        return END
    keyboard = [
        [InlineKeyboardButton(p["name"], callback_data=f"ed_{cat_id}__{p['id']}")]
        for cat_id, p in products
    ]
    await update.message.reply_text("Quel produit modifier ?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_EDIT_SELECT


async def admin_edit_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, rest = query.data.split("ed_", 1)
    cat_id, product_id = rest.split("__", 1)
    context.user_data["admin_ed_cat"] = cat_id
    context.user_data["admin_ed_prod"] = product_id
    await query.edit_message_text(
        "Quel champ modifier ?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Nom", callback_data="edfield_name")],
            [InlineKeyboardButton("Description", callback_data="edfield_description")],
            [InlineKeyboardButton("Prix", callback_data="edfield_price")],
            [InlineKeyboardButton("Disponible (true/false)", callback_data="edfield_available")],
        ]),
    )
    return ADMIN_EDIT_FIELD


async def admin_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    field = query.data[8:]
    context.user_data["admin_ed_field"] = field
    await query.edit_message_text(f"Nouvelle valeur pour *{field}* :", parse_mode="Markdown")
    return ADMIN_EDIT_VALUE


async def admin_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    field = context.user_data["admin_ed_field"]
    if field == "price":
        try:
            value = float(raw.replace(",", "."))
        except ValueError:
            await update.message.reply_text("Prix invalide. Entrez un nombre (ex. 12.50) :")
            return ADMIN_EDIT_VALUE
    elif field == "available":
        if raw.lower() in ("true", "yes", "1", "oui"):
            value = True
        elif raw.lower() in ("false", "no", "0", "non"):
            value = False
        else:
            await update.message.reply_text("Entrez true ou false :")
            return ADMIN_EDIT_VALUE
    else:
        value = raw
    catalog = load_catalog(config.CATALOG_PATH)
    catalog = edit_product(catalog, context.user_data["admin_ed_cat"], context.user_data["admin_ed_prod"], field, value)
    save_catalog(catalog, config.CATALOG_PATH)
    await update.message.reply_text(f"✅ {field} mis à jour.")
    return END


# ── Admin: /setproductimage ───────────────────────────────────────────────────

async def admin_img_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update):
        return END
    catalog = load_catalog(config.CATALOG_PATH)
    products = _all_products(catalog)
    if not products:
        await update.message.reply_text("Aucun produit dans le catalogue.")
        return END
    keyboard = [
        [InlineKeyboardButton(p["name"], callback_data=f"img_{cat_id}__{p['id']}")]
        for cat_id, p in products
    ]
    await update.message.reply_text("Pour quel produit définir l'image ?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_IMG_SELECT


async def admin_img_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, rest = query.data.split("img_", 1)
    cat_id, product_id = rest.split("__", 1)
    context.user_data["admin_img_cat"] = cat_id
    context.user_data["admin_img_prod"] = product_id
    await query.edit_message_text("Envoyez-moi une photo pour ce produit :")
    return ADMIN_IMG_UPLOAD


async def admin_img_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.photo:
        await update.message.reply_text("Veuillez envoyer une photo.")
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
    await update.message.reply_text("✅ Image du produit enregistrée.")
    return END


# ── Admin: /importproducts ────────────────────────────────────────────────────

async def admin_import_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update):
        return END
    catalog = load_catalog(config.CATALOG_PATH)
    keyboard = [
        [InlineKeyboardButton(cat["name"], callback_data=f"importcat_{cat['id']}")]
        for cat in catalog["categories"]
    ]
    await update.message.reply_text(
        "Dans quelle catégorie importer les produits ?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ADMIN_IMPORT_CAT


async def admin_import_cat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["admin_import_category"] = query.data[len("importcat_"):]
    await query.edit_message_text(
        "Envoyez le tableau JSON des produits à importer :\n\n"
        "Format : [{\"name\":\"...\", \"description\":\"...\", \"price\":20.0}, ...]"
    )
    return ADMIN_IMPORT_JSON


async def admin_import_json(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        products_data = json.loads(update.message.text.strip())
        if not isinstance(products_data, list):
            raise ValueError("Not a list")
    except (json.JSONDecodeError, ValueError):
        await update.message.reply_text(
            "JSON invalide. Assurez-vous d'envoyer un tableau : [{...}, {...}]"
        )
        return ADMIN_IMPORT_JSON

    catalog = load_catalog(config.CATALOG_PATH)
    cat_id = context.user_data["admin_import_category"]
    count = 0
    errors = []
    for i, item in enumerate(products_data):
        try:
            catalog = add_product_from_json(catalog, cat_id, item)
            count += 1
        except Exception as e:
            errors.append(f"Produit {i+1} : {e}")

    save_catalog(catalog, config.CATALOG_PATH)
    msg = f"✅ {count} produit(s) ajouté(s)."
    if errors:
        msg += "\n\n⚠️ Erreurs :\n" + "\n".join(errors)
    await update.message.reply_text(msg)
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
            PROD_MIX_SELECT: [
                CallbackQueryHandler(select_mix, pattern="^mix_"),
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

    import_conv = ConversationHandler(
        entry_points=[CommandHandler("importproducts", admin_import_start)],
        states={
            ADMIN_IMPORT_CAT: [CallbackQueryHandler(admin_import_cat, pattern="^importcat_")],
            ADMIN_IMPORT_JSON: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_import_json)],
        },
        fallbacks=[],
    )

    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_order))
    app.add_handler(customer_conv)
    app.add_handler(add_conv)
    app.add_handler(remove_conv)
    app.add_handler(edit_conv)
    app.add_handler(img_conv)
    app.add_handler(import_conv)
    app.add_handler(CommandHandler("listproducts", cmd_list_products))
    app.add_handler(CommandHandler("orders", cmd_orders))
    app.add_handler(CommandHandler("paid", cmd_paid))

    logger.info("Bot démarré. Appuyez sur Ctrl+C pour arrêter.")
    app.run_polling()


if __name__ == "__main__":
    main()
