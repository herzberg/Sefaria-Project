# -*- coding: utf-8 -*-
import regex as re
from copy import deepcopy
import pytest

import sefaria.model as model


def test_index_title_setter():
    title = 'Test Index Name'
    d = {
         "categories" : [
            "Liturgy"
        ],
        "title" : title,
        "schema" : {
            "titles" : [
                {
                    "lang" : "en",
                    "text" : title,
                    "primary" : True
                },
                {
                    "lang" : "he",
                    "text" : "דוגמא",
                    "primary" : True
                }
            ],
            "nodeType" : "JaggedArrayNode",
            "depth" : 2,
            "sectionNames" : [
                "Section",
                "Line"
            ],
            "addressTypes" : [
                "Integer",
                "Integer"
            ],
            "key": title
        },
    }
    idx = model.Index(d)
    assert idx.title == title
    assert idx.nodes.key == title
    assert idx.nodes.primary_title("en") == title
    assert getattr(idx, 'title') == title
    idx.save()

    new_title = "Changed Test Index"
    new_heb_title = "דוגמא אחרי שינוי"
    idx.title = new_title

    assert idx.title == new_title
    assert idx.nodes.key == new_title
    assert idx.nodes.primary_title("en") == new_title
    assert getattr(idx, 'title') == new_title

    idx.set_title(new_heb_title, 'he')
    assert idx.nodes.primary_title('he') == new_heb_title


    third_title = "Third Attempt"
    setattr(idx, 'title', third_title)
    assert idx.title == third_title
    assert idx.nodes.key == third_title
    assert idx.nodes.primary_title("en") == third_title
    assert getattr(idx, 'title') == third_title
    idx.delete()


def test_index_methods():
    assert model.Index().load({"title": "Rashi"}).is_commentary()
    assert not model.Index().load({"title": "Exodus"}).is_commentary()


def test_get_index():
    r = model.get_index("Rashi on Exodus")
    assert isinstance(r, model.CommentaryIndex)
    assert u'Rashi on Exodus' == r.title
    assert u'Rashi on Exodus' in r.titleVariants
    assert u'Rashi' not in r.titleVariants
    assert u'Exodus' not in r.titleVariants

    r = model.get_index("Exodus")
    assert isinstance(r, model.Index)
    assert r.title == u'Exodus'


def test_text_helpers():
    res = model.library.get_commentary_version_titles()
    assert u'Rashbam on Genesis' in res
    assert u'Rashi on Bava Batra' in res
    assert u'Bartenura on Mishnah Oholot' in res

    res = model.library.get_commentary_version_titles("Rashi")
    assert u'Rashi on Bava Batra' in res
    assert u'Rashi on Genesis' in res
    assert u'Rashbam on Genesis' not in res

    res = model.library.get_commentary_version_titles(["Rashi", "Bartenura"])
    assert u'Rashi on Bava Batra' in res
    assert u'Rashi on Genesis' in res
    assert u'Bartenura on Mishnah Oholot' in res
    assert u'Rashbam on Genesis' not in res

    res = model.library.get_commentary_version_titles_on_book("Exodus")
    assert u'Ibn Ezra on Exodus' in res
    assert u'Ramban on Exodus' in res
    assert u'Rashi on Genesis' not in res

    cats = model.library.get_text_categories()
    assert u'Tanach' in cats
    assert u'Torah' in cats
    assert u'Prophets' in cats
    assert u'Commentary' in cats


def test_index_update():
    '''
    :return: Test:
        index creation from legacy form
        update() function
        update of Index, like what happens on the frontend, doesn't whack hidden attrs
    '''
    ti = "Test Iu"
    model.IndexSet({"title": ti}).delete()

    i = model.Index({
        "title": ti,
        "heTitle": u"כבכב",
        "titleVariants": [ti],
        "sectionNames": ["Chapter", "Paragraph"],
        "categories": ["Musar"],
        "lengths": [50, 501]
    }).save()
    i = model.Index().load({"title": ti})
    assert "Musar" in i.categories
    assert i.nodes.lengths == [50, 501]

    i = model.Index().update({"title": ti}, {
        "title": ti,
        "heTitle": u"כבכב",
        "titleVariants": [ti],
        "sectionNames": ["Chapter", "Paragraph"],
        "categories": ["Philosophy"]
    })
    i = model.Index().load({"title": ti})
    assert "Musar" not in i.categories
    assert "Philosophy" in i.categories
    assert i.nodes.lengths == [50, 501]

    model.IndexSet({"title": ti}).delete()


def test_index_delete():
    #Simple Text

    #Commentator
    pass



@pytest.mark.deep
def test_index_name_change():

    #Simple Text
    tests = [
        (u"Exodus", u"Movement of Ja People"),  # Simple Text
        (u"Rashi", u"The Vintner")              # Commentator
    ]

    for old, new in tests:
        for cnt in dep_counts(new).values():
            assert cnt == 0

        old_counts = dep_counts(old)

        index = model.Index().load({"title": old})
        old_index = deepcopy(index)
        #new_in_alt = new in index.titleVariants
        index.title = new
        index.save()
        assert old_counts == dep_counts(new)

        index.title = old
        #if not new_in_alt:
        if getattr(index, "titleVariants", None):
            index.titleVariants.remove(new)
        index.save()
        #assert old_index == index   #needs redo of titling, above, i suspect
        assert old_counts == dep_counts(old)
        for cnt in dep_counts(new).values():
            assert cnt == 0


def dep_counts(name):
    commentators = model.IndexSet({"categories.0": "Commentary"}).distinct("title")
    ref_patterns = {
        'alone': r'^{} \d'.format(re.escape(name)),
        'commentor': r'{} on'.format(re.escape(name)),
        'commentee': r'^({}) on {} \d'.format("|".join(commentators), re.escape(name))
    }

    commentee_title_pattern = r'^({}) on {} \d'.format("|".join(commentators), re.escape(name))

    ret = {
        'version title exact match': model.VersionSet({"title": name}).count(),
        'version title match commentor': model.VersionSet({"title": {"$regex": ref_patterns["commentor"]}}).count(),
        'version title match commentee': model.VersionSet({"title": {"$regex": commentee_title_pattern}}).count(),
        'history title exact match': model.HistorySet({"title": name}).count(),
        'history title match commentor': model.HistorySet({"title": {"$regex": ref_patterns["commentor"]}}).count(),
        'history title match commentee': model.HistorySet({"title": {"$regex": commentee_title_pattern}}).count(),
    }

    for pname, pattern in ref_patterns.items():
        ret.update({
            'note match ' + pname: model.NoteSet({"ref": {"$regex": pattern}}).count(),
            'link match ' + pname: model.LinkSet({"refs": {"$regex": pattern}}).count(),
            'history refs match ' + pname: model.HistorySet({"ref": {"$regex": pattern}}).count(),
            'history new refs match ' + pname: model.HistorySet({"new.refs": {"$regex": pattern}}).count()
        })

    return ret


def test_version_word_count():
    #simple
    assert model.Version().load({"title": "Genesis", "language": "he"}).word_count() == 17860
    assert model.Version().load({"title": "Rashi on Shabbat", "language": "he"}).word_count() > 0
    #complex
    assert model.Version().load({"title": "Pesach Haggadah", "language": "he"}).word_count() > 0
    assert model.Version().load({"title": "Orot", "language": "he"}).word_count() > 0
    assert model.Version().load({"title": "Ephod Bad on Pesach Haggadah"}).word_count() > 0

    #sets
    assert model.VersionSet({"title": {"$regex": "Haggadah"}}).word_count() > 200000