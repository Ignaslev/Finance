from django.db import migrations
from django.utils import timezone


INTRO = """## Trumpas atsakymas: kaip sekti išlaidas?

Išlaidų sekimas – tai reguliari pajamų ir pirkinių peržiūra, padedanti suprasti, kur per mėnesį išleidžiami pinigai. Pradžiai pakanka vieno pilno mėnesio duomenų, kelių aiškių kategorijų ir trumpos mėnesio pabaigos peržiūros. Galite rinktis užrašus, skaičiuoklę, banko įrankį ar išlaidų sekimo programėlę – svarbiausia, kad visi naudojami duomenys būtų vienoje vietoje ir būtų peržiūrimi nuosekliai.

## Išlaidų sekimo programėlė, Excel ar banko įrankis?

Mobilioji programėlė gali tikti tiems, kurie išlaidas nori įvesti iškart telefone, o Excel – tiems, kurie mėgsta patys kurti lentelę. MoneyCompass yra lietuviška naršyklėje veikianti asmeninių finansų programa: į ją patys importuojate CSV arba Excel banko išrašą, peržiūrite kategorijas ir matote išlaidas, turtą bei tikslus vienoje vietoje. Ji neprisijungia prie jūsų banko ir neprašo banko prisijungimo duomenų. Tai skirtingas veikimo būdas, ne teiginys, kad vienas įrankis tinka visiems."""


def strengthen_tracking_article(apps, schema_editor):
    Article = apps.get_model("blog", "Article")
    article = Article.objects.filter(slug="islaidu-sekimas").first()
    if article is None:
        return
    article.meta_title = "Išlaidų sekimo programėlė: praktinis vadovas | MoneyCompass"
    article.meta_description = (
        "Išlaidų sekimas be sudėtingumo: palyginkite programėlę, Excel ir banko įrankį, "
        "susikurkite kategorijas bei peržiūrėkite išlaidas pagal banko išrašą."
    )
    article.excerpt = (
        "Išlaidų sekimo programėlė, Excel ar banko įrankis? Praktinis vadovas, "
        "kaip pasirinkti būdą ir peržiūrėti savo išlaidas."
    )
    article.body = f"{INTRO}\n\n{article.body}"
    article.updated_at = timezone.now()
    article.save(update_fields=["meta_title", "meta_description", "excerpt", "body", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [("blog", "0004_alter_article_body")]

    operations = [migrations.RunPython(strengthen_tracking_article, migrations.RunPython.noop)]
