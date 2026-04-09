import json
import logging
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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
) = range(21)


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


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Send a new main menu message. Used after /start and post-checkout."""
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


# ── Catalog browsing (Task 5) ──────────────────────────────────────────────────

async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def show_product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


# ── Cart & checkout (Task 6) ───────────────────────────────────────────────────

async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def remove_from_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def checkout_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def checkout_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def checkout_delivery_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def checkout_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def checkout_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def await_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


# ── Admin commands (Task 7) ────────────────────────────────────────────────────

async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raise NotImplementedError


async def admin_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raise NotImplementedError


async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def admin_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def admin_add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def admin_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def admin_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def admin_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def admin_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def admin_remove_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


async def admin_remove_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raise NotImplementedError


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    app = Application.builder().token(config.BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AGE_GATE: [CallbackQueryHandler(age_response, pattern="^age_")],
            MAIN_MENU: [
                CallbackQueryHandler(main_menu_handler, pattern="^menu_"),
                CallbackQueryHandler(back_to_menu, pattern="^back_menu$"),
            ],
            BROWSE_CAT: [
                CallbackQueryHandler(show_products, pattern="^cat_"),
                CallbackQueryHandler(back_to_menu, pattern="^back_menu$"),
            ],
            BROWSE_PROD: [
                CallbackQueryHandler(show_product_detail, pattern="^prod_"),
                CallbackQueryHandler(show_categories, pattern="^back_cats$"),
            ],
            PROD_DETAIL: [
                CallbackQueryHandler(add_to_cart, pattern="^addcart_"),
                CallbackQueryHandler(show_products, pattern="^back_prods_"),
            ],
            CART: [
                CallbackQueryHandler(remove_from_cart, pattern="^remcart_"),
                CallbackQueryHandler(checkout_name, pattern="^checkout$"),
                CallbackQueryHandler(back_to_menu, pattern="^back_menu$"),
            ],
            CHECKOUT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_phone)],
            CHECKOUT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_delivery_type)],
            CHECKOUT_DELIVERY_TYPE: [CallbackQueryHandler(checkout_address, pattern="^delivery_")],
            CHECKOUT_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, checkout_payment)],
            CHECKOUT_PAYMENT: [CallbackQueryHandler(await_screenshot, pattern="^pay_")],
            AWAIT_SCREENSHOT: [
                MessageHandler(filters.PHOTO, await_screenshot),
                MessageHandler(filters.TEXT & ~filters.COMMAND, await_screenshot),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv)
    app.run_polling()


if __name__ == "__main__":
    main()
