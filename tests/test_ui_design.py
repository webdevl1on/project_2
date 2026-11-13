"""Presentation contracts, actual authenticated HTML and unchanged ACL boundaries."""
from pathlib import Path
import json,re
from tests.test_access_control import acl_store,rule
from tests.test_access_http import web,sign_in
from app.main import app
from app.templating import templates

ROOT=Path(__file__).resolve().parents[1]

def test_every_full_document_uses_the_shared_layout():
    pages=[]
    for path in (ROOT/'app/templates').rglob('*.html'):
        source=path.read_text()
        templates.env.get_template(str(path.relative_to(ROOT/'app/templates')))
        if path.parent.name=='layouts':continue
        assert '<!doctype' not in source.lower(),str(path)
        if "extends 'layouts/" in source:pages.append(path)
    assert len(pages)==40
    base=(ROOT/'app/templates/layouts/base.html').read_text()
    assert base.index('theme_manager.js')<base.index('bootstrap.min.css')
    assert base.count('security_session.html')==1

def test_shared_components_escape_values_and_retain_accessibility():
    markup=templates.env.from_string("{% from 'components/ui.html' import card,status,restricted %}{% call card(title) %}{{ status(value) }}{{ restricted('Реквізити') }}{% endcall %}").render(title='<script>bad</script>',value='<img onerror=bad>')
    assert '<script>' not in markup and '<img ' not in markup
    assert '&lt;script&gt;' in markup and 'Доступ обмежено' in markup

def test_shell_reuses_csrf_roles_and_safe_subject_projection(web):
    client,db,ids,_=web
    login=client.get('/auth/login');assert login.status_code==200
    assert 'theme_manager.js' in login.text and 'id="app-sidebar"' not in login.text
    sign_in(client,'admin')
    for url in ['/persons','/person-positions','/staff/history','/events','/admin','/admin/users','/admin/access','/admin/backups','/account/security','/account/sessions','/account/password','/docs','/redoc',f'/person_full_info/{ids["people"][1]}']:
        response=client.get(url);assert response.status_code==200,(url,response.text[:300])
        assert response.text.lower().count('<!doctype html>')==1,url
        assert response.text.count('id="app-sidebar"')==1,url
        assert 'data-bs-scroll="true"' in response.text and 'name="csrf"' in response.text
        assert 'ui_components.css' in response.text
    rule(db,ids,unit=ids['company']);sign_in(client,'user')
    response=client.get(f'/person_full_info/{ids["people"][1]}')
    assert response.status_code==200
    assert 'data-profile-card="basic"' in response.text
    assert 'data-profile-card="documents"' not in response.text
    assert 'data-profile-card="exams"' not in response.text
    assert 'SECRET-DOCUMENT' not in response.text and 'SECRET-DIAGNOSIS' not in response.text
    assert '<span>Адміністрування</span>' not in response.text
    assert client.get('/admin/backups').status_code==403
    assert 'href="/admin/organization"' not in response.text
    rule(db,ids,category='organization',unit=ids['company'])
    assert 'href="/admin/organization"' in client.get('/persons').text

def test_theme_never_requires_a_new_settings_route():
    # The preference is local, without another data/API/security boundary.
    source=(ROOT/'app/static/js/theme_manager.js').read_text()
    assert 'fetch(' not in source and 'project2:ui-theme' in source

def test_existing_dom_and_script_contracts_are_preserved():
    # Inventory captured before the refactor, without database values or personal data.
    baseline=json.loads((ROOT/'tests/ui_template_contracts.json').read_text())
    for name,attributes in baseline.items():
        # Shared metadata and assets legitimately moved to the inherited shell.
        source=(ROOT/'app/templates'/name).read_text()+(ROOT/'app/templates/layouts/base.html').read_text()
        for key in ('id','name'):
            actual=set(re.findall(r'\b'+key+r'=[\'\"]([^\'\"]+)[\'\"]',source))
            assert set(attributes[key])<=actual,(name,key,set(attributes[key])-actual)
        assert set(attributes['data'])<=set(re.findall(r'\bdata-[a-z][a-z0-9-]*',source)),name
        for script in attributes['scripts']:assert script in source,(name,script)
