"""
Djagno Context Processors, for decorating all HTTP request with common data.
"""
from datetime import datetime

from sefaria.settings import *
from sefaria.model import library, NotificationSet
from sefaria.model.user_profile import unread_notifications_count_for_user
from sefaria.summaries import get_toc, get_toc_json
from sefaria.utils import calendars


def global_settings(request):
    return {
        "SEARCH_URL":             SEARCH_HOST,
        "SEARCH_INDEX_NAME":      SEARCH_INDEX_NAME,
        "GOOGLE_ANALYTICS_CODE":  GOOGLE_ANALYTICS_CODE,
        "MIXPANEL_CODE":          MIXPANEL_CODE,
        "DEBUG":                  DEBUG,
        "OFFLINE":                OFFLINE,
        "GLOBAL_WARNING":         GLOBAL_WARNING,
        "GLOBAL_WARNING_MESSAGE": GLOBAL_WARNING_MESSAGE,
        }


def titles_json(request):
    return {"titlesJSON": library.get_text_titles_json()}


def toc(request):
    return {"toc": get_toc(), "toc_json": get_toc_json()}


def embed_page(request):
    return {"EMBED": "embed" in request.GET}


def language_settings(request):

    # CONTENT
    # Pull language setting from cookie or Accept-Lanugage header or default to english
    content = request.COOKIES.get('contentLang') or request.LANGUAGE_CODE or 'english'
    # URL parameter trumps cookie
    content = request.GET.get("lang", content)
    content = "bilingual" if content in ("bi", "he-en", "en-he") else content
    content = 'hebrew' if content in ('he', 'he-il') else content
    content = "english" if content in ('en') else content
    # Don't allow languages other than what we currently handle
    content = 'english' if content not in ('english', 'hebrew', 'bilingual') else content

    # INTERFACE
    # Pull language setting from cookie or Accept-Lanugage header or default to english
    interface = request.COOKIES.get('interfaceLang') or request.LANGUAGE_CODE or 'english'
    interface = 'hebrew' if interface in ('he', 'he-il') else interface
    # Don't allow languages other than what we currently handle
    interface = 'english' if interface not in ('english', 'hebrew') else interface

    return {"contentLang": content, "interfaceLang": interface}


def notifications(request):
    if not request.user.is_authenticated():
        return {}
    notifications = NotificationSet().recent_for_user(request.user.id)
    unread_count  = unread_notifications_count_for_user(request.user.id)
    return {"notifications": notifications, "notifications_count": unread_count }


def calendar_links(request):
    parasha  = calendars.this_weeks_parasha(datetime.now())
    daf      = calendars.daf_yomi(datetime.now())
    
    parasha_link  = "<a href='/%s'>%s: %s</a>" % (parasha["ref"], parasha["parasha"], parasha["ref"])
    haftara_link  = " ".join(["<a href='/%s'>%s</a>" % (h, h) for h in parasha["haftara"]])
    daf_yomi_link = "<a href='/%s'>%s</a>" % (daf["url"], daf["name"])

    return {
        "parasha_link": parasha_link, 
        "haftara_link": haftara_link,
        "daf_yomi_link": daf_yomi_link
        }
