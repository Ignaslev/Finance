from django.conf import settings
from moneycoach.seo import _json_ld, organization_schema, website_schema


def _site_url(): return settings.SITE_URL.rstrip("/")
def _org(): return organization_schema()
def _website(): return website_schema()
def _context(title, description, path, schema):
    url = f"{_site_url()}{path}"
    return {"seo_title":title,"seo_description":description,"seo_canonical_url":url,"seo_alternate_lt_url":url,"seo_alternate_en_url":url,"seo_image_url":f"{_site_url()}/static/img/landing-dashboard-lt.png","seo_locale":"lt_LT","seo_schema":_json_ld(schema)}
def article_index_seo_context():
    path="/straipsniai/"; url=f"{_site_url()}{path}"; description="Praktiniai straipsniai apie asmeninių finansų valdymą, biudžetą, išlaidų sekimą ir finansinius tikslus."
    return _context("Asmeniniai finansai: straipsniai ir patarimai | MoneyCompass",description,path,{"@context":"https://schema.org","@graph":[_org(),_website(),{"@type":"CollectionPage","url":url,"name":"MoneyCompass straipsniai","description":description,"inLanguage":"lt","isPartOf":{"@id":f"{_site_url()}/#website"},"publisher":{"@id":f"{_site_url()}/#organization"}}]})
def article_seo_context(article):
    path=article.get_absolute_url(); url=f"{_site_url()}{path}"; image=f"{_site_url()}/static/img/landing-dashboard-lt.png"
    schema={"@context":"https://schema.org","@graph":[_org(),_website(),{"@type":"Article","mainEntityOfPage":url,"headline":article.title,"description":article.meta_description,"image":image,"datePublished":article.published_at.isoformat(),"dateModified":article.updated_at.isoformat(),"inLanguage":"lt","isPartOf":{"@id":f"{_site_url()}/#website"},"author":{"@id":f"{_site_url()}/#organization"},"publisher":{"@id":f"{_site_url()}/#organization"}},{"@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":"MoneyCompass","item":_site_url()},{"@type":"ListItem","position":2,"name":"Straipsniai","item":f"{_site_url()}/straipsniai/"},{"@type":"ListItem","position":3,"name":article.title,"item":url}]}]}
    return _context(article.seo_title,article.meta_description,path,schema)
