"""
Query count of grouped, "incomplete" model choice widgets.

Selectize and DualSelector are built on IncompleteSelectMixin. If the queryset has more options than the
widget's max_prefetch_choices, only that many are rendered. The widget is then marked as `incomplete`, and the
client fetches the remaining options on demand: it sends a GET request to the form's view
(`?field=<form>.<field>&offset=…` or `&search=…`), and IncompleteSelectResponseMixin._fetch_options() answers
with JSON.

With group_field_name='state', each option is placed in an <optgroup> named after the related State. Getting
that name reads the related object, so without select_related() it costs one query per option (N+1): about 250
queries for one render or one page of results. IncompleteSelectMixin.select_related_group() joins the group
relation into the choice query, both when rendering and in the lookup response.

These tests use 3 states with 7 counties each and max_prefetch_choices=10, so the field is incomplete and its
options span several groups. They check:
- test_grouped_render_queries: rendering the field takes a constant number of queries and produces optgroups.
- test_grouped_lookup_queries: the first page of the lookup endpoint takes a constant number of queries, holds
  max_prefetch_choices options, is flagged `incomplete`, and gives each option its group name.
"""
import json
import pytest

from django.forms import Form, models
from django.test import RequestFactory

from formset.views import FormView
from formset.widgets import Selectize

from testapp.models import County, State


class CountyForm(Form):
    county = models.ModelChoiceField(
        queryset=County.objects.all(),
        widget=Selectize(search_lookup='name__icontains', group_field_name='state'),
    )


class CountyView(FormView):
    form_class = CountyForm


@pytest.fixture
def counties(db):
    # The migration-seeded data may already be flushed by a transactional test in the same worker,
    # so start from a known, small data set.
    County.objects.all().delete()
    State.objects.all().delete()
    for code in ('AA', 'BB', 'CC'):
        state = State.objects.create(code=code, name=f"State {code}")
        County.objects.bulk_create(County(state=state, name=f"County {code} {n}") for n in range(7))
    # make the field incomplete: fewer prefetched options than counties
    CountyForm.base_fields['county'].widget.max_prefetch_choices = 10
    yield
    CountyForm.base_fields['county'].widget.max_prefetch_choices = Selectize.max_prefetch_choices


@pytest.mark.usefixtures('counties')
def test_grouped_render_queries(django_assert_max_num_queries):
    form = CountyForm()
    with django_assert_max_num_queries(4):
        html = str(form['county'])
    assert 'incomplete' in html
    assert '<optgroup label="State AA">' in html


@pytest.mark.usefixtures('counties')
def test_grouped_lookup_queries(django_assert_max_num_queries):
    request = RequestFactory().get(
        '/', {'field': '__default__.county', 'offset': 0}, HTTP_ACCEPT='application/json',
    )
    with django_assert_max_num_queries(4):
        response = CountyView.as_view()(request)
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data['count'] == 10
    assert data['incomplete'] is True
    assert [o['optgroup'] for o in data['options']] == ["State AA"] * 7 + ["State BB"] * 3
