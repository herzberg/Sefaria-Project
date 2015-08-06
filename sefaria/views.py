from datetime import datetime, timedelta
import json
from urlparse import urlparse
from collections import defaultdict
from random import choice

from django.utils.translation import ugettext as _
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.template.response import TemplateResponse
from django.utils.http import is_safe_url
from django.contrib.auth import authenticate
from django.contrib.auth import REDIRECT_FIELD_NAME, login as auth_login, logout as auth_logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.sites.models import get_current_site
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

import sefaria.model as model
import sefaria.system.cache as scache

from sefaria.client.util import jsonResponse, subscribe_to_announce
from sefaria.summaries import update_summaries, save_toc_to_db
from sefaria.forms import NewUserForm
from sefaria.settings import MAINTENANCE_MESSAGE
from sefaria.model.user_profile import UserProfile
from sefaria.model.group import GroupSet
from sefaria.model.translation_request import count_completed_translation_requests
from sefaria.export import export_all as start_export_all
from sefaria.datatype.jagged_array import JaggedTextArray

# noinspection PyUnresolvedReferences
from sefaria.utils.users import user_links
from sefaria.system.exceptions import InputError
from sefaria.system.database import db
from sefaria.utils.hebrew import is_hebrew

import logging
logger = logging.getLogger(__name__)


def register(request):
    if request.user.is_authenticated():
        return HttpResponseRedirect("/login")

    next = request.REQUEST.get('next', '')

    if request.method == 'POST':
        form = NewUserForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            user = authenticate(email=form.cleaned_data['email'],
                                password=form.cleaned_data['password1'])
            auth_login(request, user)
            UserProfile(id=user.id).assign_slug().save()
            if "noredirect" in request.POST:
                return HttpResponse("ok")
            else:
                next = request.POST.get("next", "/") + "?welcome=to-sefaria"
                return HttpResponseRedirect(next)
    else:
        form = NewUserForm()

    return render_to_response("registration/register.html", 
                                {'form' : form, 'next': next}, 
                                RequestContext(request))


@sensitive_post_parameters()
@csrf_protect
@never_cache
def login(request, template_name='registration/login.html',
          redirect_field_name=REDIRECT_FIELD_NAME,
          authentication_form=AuthenticationForm,
          current_app=None, extra_context=None):
    """
    Displays the login form and handles the login action.
    """
    redirect_to = request.REQUEST.get(redirect_field_name, '')

    if request.method == "POST":
        form = authentication_form(data=request.POST)
        if form.is_valid():
            # Ensure the user-originating redirection url is safe.
            if not is_safe_url(url=redirect_to, host=request.get_host()):
                redirect_to = settings.LOGIN_REDIRECT_URL

            # Okay, security check complete. Log the user in.
            auth_login(request, form.get_user())

            if request.session.test_cookie_worked():
                request.session.delete_test_cookie()

            return HttpResponseRedirect(redirect_to)
    else:
        form = authentication_form(request)

    request.session.set_test_cookie()

    current_site = get_current_site(request)

    context = {
        'form': form,
        redirect_field_name: redirect_to,
        'site': current_site,
        'site_name': current_site.name,
    }
    if extra_context is not None:
        context.update(extra_context)
    return TemplateResponse(request, template_name, context,
                            current_app=current_app)


def logout(request, next_page=None,
           template_name='registration/logged_out.html',
           redirect_field_name='next',
           current_app=None, extra_context=None):
    """
    Logs out the user and displays 'You are logged out' message.
    """
    auth_logout(request)
    redirect_to = request.REQUEST.get(redirect_field_name, '')
    if redirect_to:
        netloc = urlparse(redirect_to)[1]
        # Security check -- don't allow redirection to a different host.
        if not (netloc and netloc != request.get_host()):
            return HttpResponseRedirect(redirect_to)

    if next_page is None:
        current_site = get_current_site(request)
        context = {
            'site': current_site,
            'site_name': current_site.name,
            'title': _('Logged out')
        }
        if extra_context is not None:
            context.update(extra_context)
        return TemplateResponse(request, template_name, context,
                                current_app=current_app)
    else:
        # Redirect to this page until the session has been cleared.
        return HttpResponseRedirect(next_page or request.path)


def maintenance_message(request):
    return render_to_response("static/maintenance.html",
                                {"message": MAINTENANCE_MESSAGE},
                                RequestContext(request))


def accounts(request):
    return render_to_response("registration/accounts.html", 
                                {"createForm": UserCreationForm(),
                                "loginForm": AuthenticationForm() }, 
                                RequestContext(request))


def subscribe(request, email):
    if subscribe_to_announce(email):
        return jsonResponse({"status": "ok"})
    else:
        return jsonResponse({"error": "Sorry, there was an error."})


def linker_js(request):
    attrs = {
        "book_titles": json.dumps(model.library.full_title_list("en", with_commentary=True, with_commentators=False)
                      + model.library.full_title_list("he", with_commentary=True, with_commentators=False))
    }
    return render_to_response("js/linker.js", attrs, RequestContext(request), mimetype= "text/javascript")


def title_regex_api(request, titles):
    if request.method == "GET":
        cb = request.GET.get("callback", None)
        titles = set(titles.split("|"))
        res = {}
        errors = []
        for title in titles:
            lang = "he" if is_hebrew(title) else "en"
            try:
                re_string = model.library.get_regex_string(title, lang, for_js=True)
                res[title] = re_string
            except (AttributeError, AssertionError) as e:
                logger.warning(u"Library._build_ref_from_string() failed to create regex for: {}.  {}".format(title, e))
                errors.append(u"{} : {}".format(title, e))
        if len(errors):
            res["error"] = errors
        resp = jsonResponse(res, cb)
        resp['Access-Control-Allow-Origin'] = '*'
        return resp


def bulktext_api(request, refs):
    """
    Used by the linker.
    :param request:
    :param refs:
    :return:
    """
    if request.method == "GET":
        cb = request.GET.get("callback", None)
        refs = set(refs.split("|"))
        res = {}
        for tref in refs:
            try:
                oref = model.Ref(tref)
                lang = "he" if is_hebrew(tref) else "en"
                he = model.TextChunk(oref, "he").text
                en = model.TextChunk(oref, "en").text
                res[tref] = {
                    'he': he if isinstance(he, basestring) else JaggedTextArray(he).flatten_to_string(),  # these could be flattened on the client, if need be.
                    'en': en if isinstance(en, basestring) else JaggedTextArray(en).flatten_to_string(),
                    'lang': lang,
                    'ref': oref.normal(),
                    'heRef': oref.he_normal(),
                    'url': oref.url()
                }
            except (InputError, ValueError, AttributeError) as e:
                referer = request.META.get("HTTP_REFERER", "unknown page")
                logger.warning(u"Linker failed to parse {} from {} : {}".format(tref, referer, e))
                res[tref] = {"error": 1}
        resp = jsonResponse(res, cb)
        resp['Access-Control-Allow-Origin'] = '*'
        return resp

@staff_member_required
def reset_cache(request):
    scache.reset_texts_cache()
    global user_links
    user_links = {}
    return HttpResponseRedirect("/?m=Cache-Reset")

"""@staff_member_required
def view_cached_elem(request, title):
    return HttpResponse(get_template_cache('texts_list'), status=200)

@staff_member_required
def del_cached_elem(request, title):
    delete_template_cache('texts_list')
    toc_html = get_template_cache('texts_list')
    return HttpResponse(toc_html, status=200)"""


@staff_member_required
def reset_counts(request):
    model.refresh_all_states()
    return HttpResponseRedirect("/?m=Counts-Rebuilt")


@staff_member_required
def rebuild_toc(request):
    update_summaries()
    return HttpResponseRedirect("/?m=TOC-Rebuilt")


@staff_member_required
def rebuild_counts_and_toc(request):
    model.refresh_all_states()
    return HttpResponseRedirect("/?m=Counts-&-TOC-Rebuilt")


@staff_member_required
def save_toc(request):
    save_toc_to_db()
    return HttpResponseRedirect("/?m=TOC-Saved")


@staff_member_required
def rebuild_commentary_links(request, title):
    from sefaria.helper.link import rebuild_commentary_links as rebuild
    rebuild(title, request.user.id)
    return HttpResponseRedirect("/?m=Commentary-Links-Rebuilt-on-%s" % title)


@staff_member_required
def rebuild_citation_links(request, title):
    from sefaria.helper.link import rebuild_links_from_text as rebuild
    rebuild(title, request.user.id)
    return HttpResponseRedirect("/?m=Citation-Links-Rebuilt-on-%s" % title)


@staff_member_required
def delete_citation_links(request, title):
    from sefaria.helper.link import delete_links_from_text
    delete_links_from_text(title, request.user.id)
    return HttpResponseRedirect("/?m=Citation-Links-Deleted-on-%s" % title)


@staff_member_required
def cache_stats(request):
    resp = {
        'ref_cache_size': model.Ref.cache_size()
    }
    return jsonResponse(resp)


@staff_member_required
def cache_dump(request):
    resp = {
        'ref_cache_dump': model.Ref.cache_dump()
    }
    return jsonResponse(resp)

@staff_member_required
def create_commentator_version(request, commentator, book, lang, vtitle, vsource):
    from sefaria.helper.text import create_commentator_and_commentary_version
    create_commentator_and_commentary_version(commentator, book, lang, vtitle, vsource)
    scache.reset_texts_cache()
    return HttpResponseRedirect("/add/%s" % commentator)


@staff_member_required
def export_all(request):
    start = datetime.now()
    try:
        start_export_all()
        resp = {"status": "ok"}
    except Exception, e:
        resp = {"error": str(e)}
    resp["time"] = (datetime.now()-start).seconds
    return jsonResponse(resp)


@staff_member_required
def cause_error(request):
    resp = {}
    logger.error("This is a simple error")
    try:
        erorr = excepting
    except Exception as e:
        logger.exception('An Exception has occured in thre code')
    erorr = error
    return jsonResponse(resp)


@staff_member_required
def list_contest_results(request):
    """
    List results for last week's mini contest on translation requests.
    """
    today            = datetime.today()
    end_month        = today.month if today.day >= 28 else today.month - 1
    end_month        = 12 if end_month == 0 else end_month
    contest_end      = today.replace(month=end_month, day=28, hour=0, minute=0) 
    start_month      = end_month - 1 if end_month > 1 else 12
    contest_start    = contest_end.replace(month=start_month)
    requests_query   = {"completed": True, "featured": True, "completed_date": { "$gt": contest_start, "$lt": contest_end } }
    requests         = model.TranslationRequestSet(requests_query, sort=[["featured", 1]])
    user_points      = defaultdict(int)
    user_requests    = defaultdict(int)
    total_points     = 0
    total_requests   = len(requests)
    results          = "Contest Results for %s to %s<br>" % (str(contest_start), str(contest_end))
    lottery          = []

    for request in requests:
        points = 5 if getattr(request, "featured", False) else 1
        user_points[request.completer] += points
        user_requests[request.completer] += 1
        total_points += points

    results += "%d participants completed %d requests<br><br>" % (len(user_requests.keys()), total_requests)

    for user in user_points.keys():
        profile = model.user_profile.UserProfile(id=user)
        results += "%s: completed %d requests for %d points (%s)<br>" % (profile.full_name, user_requests[user], user_points[user], profile.email)
        lottery += ([user] * user_points[user])

    if len(lottery):
        winner = choice(lottery)
        winner = model.user_profile.UserProfile(id=winner)

        results += "<br>The winner is: %s (%s)" % (winner.full_name, winner.email)

    return HttpResponse(results)


@staff_member_required
def translation_requests_stats(request):
    return HttpResponse(count_completed_translation_requests().replace("\n", "<br>"))


@staff_member_required
def sheet_stats(request):
    from dateutil.relativedelta import relativedelta
    html  = ""
    start = datetime.today().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    months = 30
    for i in range(months):
        end   = start
        start = end - relativedelta(months=1)
        query = {"dateCreated": {"$gt": start.isoformat(), "$lt": end.isoformat()}}
        n = db.sheets.find(query).distinct("owner")
        html = "%s: %d\n%s" % (start.strftime("%b %y"), len(n), html)

    html = "Unique Source Sheet creators per month:\n\n" + html
    return HttpResponse("<pre>" + html + "<pre>")

