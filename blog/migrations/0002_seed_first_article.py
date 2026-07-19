from django.db import migrations
from django.utils import timezone


BODY = """Asmeninių finansų valdymas prasideda ne nuo tobulo biudžeto ar sudėtingos lentelės. Pirmas tikslas yra paprastesnis: suprasti, kur keliauja pinigai ir ką norite su jais pasiekti.

## Pradėkite nuo viso vaizdo

Surinkite į vieną vietą pajamas, kasdienes išlaidas, turimą turtą, įsipareigojimus ir jau turimus finansinius tikslus. Nebūtina iš karto visko suvesti idealiai. Pirmas mėnuo skirtas pastebėti pasikartojančius sprendimus, o ne save vertinti.

## Sekite išlaidas pagal prasmingas kategorijas

Kategorijos turi atsakyti į klausimą, kuris jums svarbus. Maistas, būstas, transportas, prenumeratos, laisvalaikis ir sveikata daugeliui yra gera pradžia. Jei kategorija nepadeda priimti sprendimo, ją galima sujungti su kita.

## Biudžetas yra planas, ne bausmė

Biudžetas padeda iš anksto nuspręsti, kam skirsite pinigus. Palyginkite planą su faktinėmis išlaidomis mėnesio pabaigoje ir pakoreguokite kitą mėnesį. Veikiantis planas prisitaiko prie realaus gyvenimo.

## Matykite ne tik išlaidas

Asmeniniai finansai apima ir santaupas, investicijas, skolas bei tikslus. Kai šie duomenys matomi vienoje vietoje, lengviau suprasti bendrą kryptį, o ne vertinti kiekvieną pirkinį atskirai.

## Sukurkite paprastą peržiūros rutiną

Skirkite kelias minutes kartą per savaitę operacijoms peržiūrėti, o kartą per mėnesį įvertinkite kategorijas, turto pokytį ir tikslų progresą. Reguliarumas yra naudingesnis už retą, labai išsamią analizę.

MoneyCompass leidžia rankiniu būdu importuoti CSV arba Excel banko išrašus, suskirstyti operacijas į kategorijas ir matyti išlaidas, turtą, investicijas bei tikslus viename privačiame vaizde. Programa neprisijungia prie jūsų banko ir neteikia individualių finansinių rekomendacijų."""


def seed(apps, schema_editor):
    Article = apps.get_model("blog", "Article")
    Article.objects.get_or_create(slug="asmeniniu-finansu-valdymas", defaults={"language":"lt","title":"Asmeninių finansų valdymas: kaip pradėti nuo nulio","meta_title":"Asmeninių finansų valdymas: kaip pradėti | MoneyCompass","meta_description":"Sužinokite, kaip pradėti valdyti asmeninius finansus: sekti išlaidas, planuoti biudžetą ir matyti savo finansinį vaizdą.","excerpt":"Paprastas būdas pradėti sekti išlaidas, planuoti biudžetą ir matyti bendrą savo finansų vaizdą.","body":BODY,"status":"published","published_at":timezone.now()})


class Migration(migrations.Migration):
    dependencies = [("blog", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
