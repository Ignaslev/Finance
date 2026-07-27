from django.db import migrations
from django.utils import timezone


BANK_STATEMENT = """Banko išrašo analizė padeda suprasti ne tik sąskaitos likutį, bet ir visą mėnesio pinigų judėjimą. Tam nereikia vertinti kiekvieno pirkimo atskirai. Pirmiausia reikia surinkti pilną laikotarpį, atskirti pervedimus, suskirstyti tikras pajamas bei išlaidas ir tik tada ieškoti pasikartojančių pokyčių.

## Trumpas atsakymas: kaip analizuoti banko išrašą?

Pasirinkite vieną pilną mėnesį, įtraukite visas naudojamas sąskaitas, atskirkite pervedimus tarp savo sąskaitų ir grąžinimus, o likusias operacijas suskirstykite į kelias aiškias kategorijas. Tada palyginkite bendras pajamas, bendras išlaidas, didžiausias kategorijas ir reguliarius mokėjimus. Užbaikite peržiūrą viena ar dviem konkrečiomis išvadomis kitam mėnesiui.

## Kodėl vien sąskaitos likučio neužtenka?

Likutis parodo padėtį vienu momentu. Jis nepaaiškina, ar mėnesio rezultatą pakeitė kasdienės išlaidos, vienas didelis pirkinys, pervedimas į kitą savo sąskaitą ar vėliau grąžintas mokėjimas. Dvi vienodą likutį turinčios sąskaitos gali slėpti visiškai skirtingus pinigų srautus.

[Lietuvos bankas](https://www.lb.lt/lt/asmeniniai-finansai) rekomenduoja pradžioje bent mėnesį žymėtis pajamas ir išlaidas. Pilnas laikotarpis apima daugumą mėnesinių mokėjimų ir suteikia realesnį pagrindą biudžetui nei kelių dienų pavyzdys.

## 1. Pasirinkite tinkamą laikotarpį

Pradėkite nuo paskutinio pilno kalendorinio mėnesio. Jei pajamos gaunamos kitu ciklu, galite rinktis laikotarpį nuo vienos pajamų dienos iki kitos, tačiau vėliau naudokite tą pačią taisyklę. Skirtingo ilgio laikotarpius lyginti sunkiau.

Jei naudojate kelis bankus ar mokėjimo korteles, eksportuokite visų jų operacijas. Vienos sąskaitos išrašas gali neparodyti kasdienių mokėjimų kitoje kortelėje ar taupymo pervedimų.

## 2. Patikrinkite duomenų ribas

Prieš skaičiuodami įsitikinkite, kad:

- sutampa pasirinkto laikotarpio pradžia ir pabaiga;
- nėra pakartotinai įkeltų tų pačių operacijų;
- sumos ir valiutos perskaitytos teisingai;
- įtrauktos grynųjų išlaidos, jei jos jums reikšmingos;
- neaiškūs pardavėjų pavadinimai palikti patikrinti.

Duomenų kokybė svarbesnė už diagramų skaičių. Vienas dvigubai įtrauktas didelis pervedimas gali iškreipti viso mėnesio išvadą.

## 3. Atskirti pervedimus, pajamas ir išlaidas

Pervedimas iš vienos savo sąskaitos į kitą nekeičia bendros finansinės padėties. Jei vienoje sąskaitoje jis rodomas kaip išlaida, o kitoje kaip pajamos, bendra suvestinė dirbtinai padidėja. Tokias poras pažymėkite kaip pervedimus.

Grąžinimą galima susieti su pradine išlaidų kategorija arba rodyti atskirai. Svarbiausia pasirinkti nuoseklią taisyklę. Darbo užmokestis, individualios veiklos pajamos ar kitos įplaukos turėtų būti atskirtos nuo savo paties pervedimų.

## 4. Naudokite nedaug prasmingų kategorijų

Pirmai analizei pakanka 6–10 pagrindinių grupių. Pavyzdžiui:

- būstas ir komunalinės paslaugos;
- maistas ir kasdienės prekės;
- transportas;
- sveikata;
- laisvalaikis;
- prenumeratos ir ryšio paslaugos;
- kitos arba dar nepatikrintos išlaidos.

Kategoriją smulkinkite tik tada, kai ji nebeatsako į konkretų klausimą. Jei „Maistas“ atrodo per plati, vėliau galite atskirti parduotuves ir kavines. Nereikia iš anksto kurti dešimčių kategorijų, kurių nenaudosite peržiūroje.

## 5. Atpažinkite reguliarius ir vienkartinius mokėjimus

Reguliarūs mokėjimai kartojasi kas mėnesį, ketvirtį ar metus. Prenumeratos, būsto mokesčiai ir draudimas dažnai sudaro pastovią bazę. Vienkartinė kelionė ar remontas neturėtų būti vertinami kaip naujas įprasto mėnesio lygis.

Peržiūrėkite ne tik didžiausias sumas, bet ir mažus pasikartojančius mokėjimus. [JAV vartotojų finansinės apsaugos biuras](https://www.consumerfinance.gov/archive/blog/track-your-spending-with-this-easy-tool/) siūlo po stebėjimo paklausti, ar mokate už paslaugas ar prenumeratas, kurių iš tikrųjų nenaudojate.

## 6. Palyginkite keturis pagrindinius rodiklius

Pirmoje banko išrašo analizėje pakanka:

- visų laikotarpio pajamų;
- visų tikrų išlaidų;
- trijų didžiausių išlaidų kategorijų;
- reguliarių mokėjimų sumos.

Jei turite ankstesnį mėnesį, palyginkite tas pačias kategorijas. Didžiausią procentinį pokytį visada patikrinkite operacijų sąraše – jį gali paaiškinti viena reta išlaida.

## 7. Paverskite skaičius sprendimu

Naudinga išvada turi būti konkretesnė nei „reikia mažiau išleisti“. Pavyzdžiui:

- kito mėnesio plane atskirai numatyti metinį draudimo mokėjimą;
- patikrinti dvi nebenaudojamas prenumeratas;
- kavinių išlaidas atskirti nuo maisto parduotuvių;
- į analizę įtraukti antrą kasdien naudojamą kortelę.

Vienas aiškus pakeitimas yra vertingesnis už ilgą pažadų sąrašą. Kitą mėnesį galėsite patikrinti, ar pakeitimas davė naudingos informacijos.

## Banko išrašo analizė su MoneyCompass

MoneyCompass leidžia rankiniu būdu importuoti CSV arba Excel banko išrašą, tvarkyti kategorijas ir matyti suvestines. Programa neprašo banko slaptažodžio ir neturi nuolatinio ryšio su sąskaita. Išsamų importo procesą rasite [MoneyCompass gide](/gidas/#operaciju-importavimas).

Jei norite įvertinti, ar toks darbo būdas jums tinka, peržiūrėkite [MoneyCompass finansų valdymo programėlės aprašymą](/finansu-valdymo-programele/). Tai stebėjimo ir organizavimo įrankis, o ne individualus finansų patarėjas.

## Banko išrašo analizės kontrolinis sąrašas

- Pasirinktas pilnas laikotarpis.
- Įtrauktos visos naudojamos sąskaitos.
- Pašalintas dvigubas pervedimų skaičiavimas.
- Patikrinti grąžinimai ir neaiškios operacijos.
- Naudojamos aiškios, palyginamos kategorijos.
- Atskirti reguliarūs ir vienkartiniai mokėjimai.
- Užrašyta bent viena konkreti išvada.

## Šaltiniai

- [Lietuvos bankas: asmeniniai finansai](https://www.lb.lt/lt/asmeniniai-finansai)
- [Consumer Financial Protection Bureau: spending tracker](https://www.consumerfinance.gov/archive/blog/track-your-spending-with-this-easy-tool/)
- [MoneyHelper: budget planner](https://www.moneyhelper.org.uk/en/everyday-money/budgeting/budget-planner)"""


BUDGET_METHODS = """Biudžeto planavimo metodai yra skirtingos taisyklės tam pačiam tikslui: iš anksto nuspręsti, kaip paskirstysite pajamas, ir vėliau palyginti planą su faktu. Metodas turi prisitaikyti prie jūsų pajamų, įsipareigojimų ir norimo detalumo, o ne atvirkščiai.

## Trumpas atsakymas: kokį biudžeto planavimo metodą rinktis?

Jei biudžetą kuriate pirmą kartą, pradėkite nuo kategorijų plano pagal realias praėjusio mėnesio išlaidas. Jei reikia griežtesnio paskirstymo, išbandykite nulinio biudžeto principą. Jei norite tik bendrų ribų, naudokite procentines grupes, tačiau jų dydžius pritaikykite sau. Kintamoms pajamoms geriausiai tinka bazinis planas, sudarytas tik iš patvirtintų pajamų.

## Pirmiausia surinkite realius skaičius

[Lietuvos bankas](https://www.lb.lt/lt/asmeniniai-finansai) asmeninį biudžetą apibrėžia kaip pajamų ir išlaidų planą ir rekomenduoja pradžioje bent mėnesį stebėti realias pajamas bei išlaidas. Tai svarbu nepriklausomai nuo pasirinkto metodo.

Jei dar nežinote, kiek išleidžiate maistui, transportui ar reguliariems mokėjimams, procentai bus spėjimas. [MoneyHelper](https://www.moneyhelper.org.uk/en/everyday-money/budgeting/budget-planner) siūlo planuojant turėti banko išrašus, sąskaitas ir pajamų dokumentus, kad įvestos sumos būtų realistiškesnės.

## 1. Kategorijų biudžetas

Tai paprasčiausias metodas: pajamos ir išlaidos suskirstomos į kelias grupes, o kiekvienai kintamai kategorijai nustatomas mėnesio orientyras.

**Tinka, kai:** norite suprasti pagrindines išlaidų kryptis ir neturite poreikio planuoti kiekvieną eurą.

**Kaip pradėti:**

- įrašykite patikimas mėnesio pajamas;
- pridėkite reguliarius įsipareigojimus;
- pagal ankstesnius duomenis nustatykite kintamų kategorijų orientyrus;
- atskirai numatykite tikslus ir nereguliarias išlaidas;
- mėnesio pabaigoje palyginkite planą su faktu.

Pradžiai pakanka būsto, maisto, transporto, sveikatos, laisvalaikio ir kitų išlaidų kategorijų. Detalumą didinkite tik tada, kai plati kategorija nebeatsako į klausimą.

## 2. Nulinio biudžeto principas

Nulinis biudžetas reiškia, kad kiekvienam planuojamam eurui iš anksto paskiriama paskirtis: išlaidoms, santaupoms, įsipareigojimams ar tikslams. „Nulis“ nereiškia, kad viską privalote išleisti. Tai reiškia, kad pajamos minus visos suplanuotos paskirtys yra lygios nuliui.

**Tinka, kai:** norite detalaus plano ir esate pasirengę jį reguliariai atnaujinti.

**Rizika:** per daug smulkus planas gali pareikalauti daugiau laiko nei suteikia naudos. Numatykite lankstumo kategoriją ir neleiskite vienam nukrypimui sugriauti viso mėnesio.

## 3. Procentinių grupių metodas

Šis metodas pajamas paskirsto į kelias plačias dalis, pavyzdžiui, būtinosioms išlaidoms, pasirenkamoms išlaidoms ir santaupoms ar skolų mokėjimui. Internete dažnai pateikiamos universalios proporcijos, tačiau jos nėra vienodai tinkamos skirtingoms pajamoms, būsto kainai, šeimos dydžiui ar finansiniams įsipareigojimams.

[JAV vartotojų finansinės apsaugos biuro](https://files.consumerfinance.gov/f/documents/cfpb_worksheet_my-spending-rule-to-live-by.pdf) darbo lapas siūlo pirmiausia išanalizuoti realų paskirstymą tarp poreikių, norų, santaupų bei skolų ir tik tada susikurti savo išlaidų taisyklę.

**Tinka, kai:** norite bendros krypties, bet ne detalaus kiekvienos kategorijos plano.

**Kaip naudoti atsakingai:** pradines proporcijas skaičiuokite iš savo duomenų ir keiskite pagal realius įsipareigojimus. Procentas yra orientyras, o ne pažadas ar universali rekomendacija.

## 4. Savaitinių ribų metodas

Iš patikimų mėnesio pajamų atimkite reguliarius mokėjimus, tikslams skirtas sumas ir žinomas nereguliarias išlaidas. Likusią kintamų išlaidų dalį paskirstykite savaitėmis.

**Tinka, kai:** mėnesio planas atrodo per ilgas ir sunku įvertinti, kiek dar galima skirti kasdienėms reikmėms.

Skirtingos savaitės nebus vienodos, todėl nepanaudota ar viršyta suma gali persikelti. Šis metodas geriausiai veikia kaip trumpesnis kontrolės taškas, o ne kaip bausmė už kiekvieną nukrypimą.

## 5. Bazinis planas kintamoms pajamoms

Kai pajamos nevienodos, biudžetą kurkite tik iš sumos, kurią pagrįstai tikitės gauti. Papildomoms pajamoms iš anksto paruoškite atskirą prioritetų sąrašą.

Galite turėti tris scenarijus:

- bazinį – pagal patvirtintas pajamas;
- mažesnių pajamų – su atidedamomis kintamomis išlaidomis;
- didesnių pajamų – nurodant, kam būtų skirta papildoma suma.

Scenarijai nėra pajamų prognozė. Jie tik parodo, kaip pasikeistų jūsų pačių planas esant kitai sumai.

## Kaip išbandyti metodą per vieną mėnesį?

1. Pasirinkite vieną metodą ir užrašykite jo taisykles.
2. Naudokite ankstesnio pilno mėnesio operacijas pradinei versijai.
3. Per mėnesį nekeiskite visos struktūros dėl vieno pirkimo.
4. Mėnesio pabaigoje įvertinkite, ką metodas padėjo pastebėti.
5. Supaprastinkite tas dalis, kurių realiai nenaudojote.

Vertinkite ne tik tai, ar neviršijote sumų. Geras metodas turi padėti paaiškinti skirtumus, numatyti nereguliarius mokėjimus ir parengti tikslesnį kitą planą.

## Biudžeto planavimas su MoneyCompass

MoneyCompass pirmiausia parodo faktines importuotas operacijas ir jų kategorijas. Šiuos duomenis galite naudoti realistiškesniam planui ir mėnesio peržiūrai. Banko išrašai importuojami rankiniu būdu iš CSV arba Excel failo, be tiesioginio banko prijungimo.

Žingsnis po žingsnio procesą rasite straipsnyje [Asmeninis biudžetas: kaip sudaryti veikiantį planą](/straipsniai/asmeninis-biudzetas/), o programos funkcijas – [MoneyCompass finansų programėlės puslapyje](/finansu-valdymo-programele/).

## Šaltiniai

- [Lietuvos bankas: asmeniniai finansai](https://www.lb.lt/lt/asmeniniai-finansai)
- [Consumer Financial Protection Bureau: spending rule worksheet](https://files.consumerfinance.gov/f/documents/cfpb_worksheet_my-spending-rule-to-live-by.pdf)
- [MoneyHelper: budget planner](https://www.moneyhelper.org.uk/en/everyday-money/budgeting/budget-planner)"""


MONTHLY_REVIEW = """Mėnesio finansų peržiūra yra trumpas procesas, per kurį patikrinate praėjusio laikotarpio pajamas, išlaidas, reguliarius mokėjimus, turtą ir tikslus. Jos tikslas nėra įvertinti kiekvieną sprendimą. Tikslas – paaiškinti svarbiausius pokyčius ir paruošti realesnį kitą mėnesį.

## Trumpas atsakymas: ką peržiūrėti mėnesio pabaigoje?

Patikrinkite, ar įtrauktos visos sąskaitos, sutvarkykite pervedimus ir neaiškias operacijas, palyginkite pajamas su išlaidomis, išskirkite didžiausius kategorijų pokyčius, peržiūrėkite reguliarius mokėjimus ir atnaujinkite turtą bei tikslus. Užbaikite dviem įrašais: ką sužinojote ir ką kitą mėnesį darysite kitaip.

## Kodėl verta turėti pastovią peržiūrą?

Kasdienės operacijos pateikia daug smulkių signalų. Mėnesio peržiūra juos sujungia į laikotarpį, kuriame matosi atlyginimas, sąskaitos, prenumeratos ir dauguma pasikartojančių išlaidų.

[Lietuvos bankas](https://www.lb.lt/lt/asmeniniai-finansai) rekomenduoja pradžioje bent vieną mėnesį sekti pajamas ir išlaidas, o vėliau pagal realius duomenis planuoti kategorijas. Peržiūra yra tiltas tarp stebėjimo ir kito plano.

## 1. Surinkite pilną mėnesį

Įtraukite visas kasdien naudojamas banko sąskaitas, mokėjimo korteles ir reikšmingas grynųjų išlaidas. Patikrinkite, ar laikotarpiai sutampa. Jei duomenis importuojate iš failų, įsitikinkite, kad tas pats išrašas neįtrauktas du kartus.

[MoneyHelper](https://www.moneyhelper.org.uk/en/everyday-money/budgeting/budget-planner) rekomenduoja planuojant turėti banko išrašus ir sąskaitas, kad naudojamos sumos būtų realesnės. Tas pats principas tinka ir mėnesio uždarymui.

## 2. Sutvarkykite išimtis prieš darydami išvadas

Pirmiausia patikrinkite:

- pervedimus tarp savo sąskaitų;
- pirkinių grąžinimus;
- neaiškius pardavėjų pavadinimus;
- operacijas be kategorijos;
- vienkartines, sezonines ar metines išlaidas.

Jei pervedimas skaičiuojamas ir kaip išlaida, ir kaip pajamos, suvestinė bus klaidinanti. Jei reta metinė įmoka sumaišoma su kasdienėmis išlaidomis, kitas mėnuo gali atrodyti dirbtinai geresnis.

## 3. Palyginkite pajamas ir išlaidas

Užrašykite bendras laikotarpio pajamas, tikras išlaidas ir jų skirtumą. Tada pažiūrėkite, kurios trys kategorijos sudarė didžiausią išlaidų dalį.

Vien bendra suma neatsako, kas pasikeitė. Jei bendros išlaidos išaugo, patikrinkite, ar:

- pakilo įprastų kategorijų lygis;
- atsirado naujas reguliarus mokėjimas;
- rezultatą pakeitė vienkartinis įvykis;
- ankstesnį mėnesį trūko dalies duomenų.

## 4. Peržiūrėkite reguliarius mokėjimus

Sudarykite pasikartojančių mokėjimų sąrašą ir pažymėkite naujus, pabrangusius ar nebenaudojamus. Mažos prenumeratos atskirai gali atrodyti nereikšmingos, todėl naudingiau matyti jų bendrą sumą.

[JAV vartotojų finansinės apsaugos biuras](https://www.consumerfinance.gov/archive/blog/track-your-spending-with-this-easy-tool/) siūlo po išlaidų stebėjimo įvertinti, ar mokate už paslaugas ar prenumeratas, kurių realiai nenaudojate.

## 5. Palyginkite planą su faktu

Jei turėjote biudžetą, kiekvienai pagrindinei kategorijai palyginkite planuotą ir faktinę sumą. Tada paaiškinkite didžiausius skirtumus.

Skirtumas savaime nėra nesėkmė. Jį galėjo sukelti kainos pokytis, sezonas, vienkartinis pirkinys ar netikslus pradinis orientyras. Priežastis padeda nuspręsti, ar kitą mėnesį keisti planą.

## 6. Atnaujinkite bendrą turto vaizdą

Pinigų srautas ir bendras turtas atsako į skirtingus klausimus. Pinigų srautas parodo, kiek per mėnesį gavote ir išleidote. Turto vaizdas apima sąskaitų likučius, santaupas, įvestas investicijas ir įsipareigojimus.

Vertes atnaujinkite tuo pačiu metu, pavyzdžiui, paskutinę mėnesio dieną. Tuomet laikotarpius bus lengviau palyginti.

## 7. Patikrinkite finansinius tikslus

Atnaujinkite tikslui skirtą sumą ir terminą, jei pasikeitė aplinkybės. Tikslų peržiūra neturi virsti automatine rekomendacija, kur laikyti ar investuoti pinigus. Ji parodo tik jūsų pačių pasirinkto plano progresą.

## 8. Užrašykite dvi išvadas

Užbaikite peržiūrą dviem trumpais sakiniais:

1. **Ką sužinojau?** Pavyzdžiui, didžiąją transporto išlaidų dalį sudarė vienas remontas, o kasdienės išlaidos beveik nepasikeitė.
2. **Ką pakeisiu?** Pavyzdžiui, kitame plane automobilio priežiūrai numatysiu atskirą nereguliarių išlaidų eilutę.

Rinkitės vieną ar du pakeitimus, kuriuos galėsite patikrinti po mėnesio. Ilgas abstrakčių tikslų sąrašas paprastai duoda mažiau naudos.

## 30 minučių mėnesio finansų peržiūros eiga

- **0–5 min.** Patikrinkite laikotarpį, sąskaitas ir dublikatus.
- **5–12 min.** Sutvarkykite pervedimus, grąžinimus ir neaiškias kategorijas.
- **12–20 min.** Palyginkite pajamas, išlaidas ir didžiausias kategorijas.
- **20–25 min.** Peržiūrėkite reguliarius mokėjimus, turtą ir tikslus.
- **25–30 min.** Užrašykite išvadas ir atnaujinkite kito mėnesio planą.

Jei procesas nuolat trunka ilgiau, sumažinkite kategorijų skaičių arba palikite tik rodiklius, kuriuos iš tikrųjų naudojate sprendimams.

## Mėnesio peržiūra su MoneyCompass

MoneyCompass leidžia importuoti CSV arba Excel banko išrašus, pataisyti kategorijas ir vienoje vietoje matyti išlaidas, sąskaitas, turtą, investicijas bei tikslus. Programa neprisijungia prie banko, todėl duomenų atnaujinimo laiką pasirenkate jūs.

Prieš pirmą peržiūrą perskaitykite [banko išrašo analizės vadovą](/straipsniai/banko-israso-analize/). Platesnį procesą rasite [asmeninių finansų valdymo vadove](/straipsniai/asmeniniu-finansu-valdymas/), o produkto veikimą – [MoneyCompass gide](/gidas/).

## Šaltiniai

- [Lietuvos bankas: asmeniniai finansai](https://www.lb.lt/lt/asmeniniai-finansai)
- [Consumer Financial Protection Bureau: spending tracker](https://www.consumerfinance.gov/archive/blog/track-your-spending-with-this-easy-tool/)
- [MoneyHelper: budget planner](https://www.moneyhelper.org.uk/en/everyday-money/budgeting/budget-planner)"""


PILLAR_PREFIX = """## Trumpas atsakymas: nuo ko pradėti valdyti asmeninius finansus?

Asmeninių finansų valdymą pradėkite nuo vieno pilno mėnesio pajamų ir išlaidų. Surinkite visų naudojamų sąskaitų operacijas, atskirkite pervedimus, suskirstykite išlaidas į kelias kategorijas ir palyginkite rezultatą su savo planu. Tada pridėkite turto, įsipareigojimų ir tikslų peržiūrą. Sistema turi padėti paaiškinti pokyčius, o ne vien kaupti skaičius.

"""


BUDGET_PREFIX = """## Trumpas atsakymas: kas yra asmeninis biudžetas?

Asmeninis biudžetas yra pasirinkto laikotarpio pajamų ir išlaidų planas. Jame pirmiausia įrašomos patikimos pajamos ir reguliarūs įsipareigojimai, tada kintamų bei nereguliarių išlaidų orientyrai ir finansiniai tikslai. Mėnesio pabaigoje planas palyginamas su faktinėmis operacijomis, o didžiausi skirtumai paaiškinami ir panaudojami kitam planui patikslinti.

"""


def publish_cluster(apps, schema_editor):
    Article = apps.get_model("blog", "Article")
    now = timezone.now()

    updates = {
        "asmeniniu-finansu-valdymas": {
            "meta_title": "Asmeninių finansų valdymas: praktinis gidas",
            "meta_description": (
                "Praktinis asmeninių finansų valdymo gidas: išlaidos, biudžetas, "
                "turtas, tikslai ir aiški mėnesio peržiūra."
            ),
            "prefix": PILLAR_PREFIX,
            "link": (
                "\n\nNorėdami pamatyti, kaip šį procesą palaiko produktas, peržiūrėkite "
                "[MoneyCompass finansų valdymo programėlę](/finansu-valdymo-programele/)."
            ),
        },
        "asmeninis-biudzetas": {
            "meta_title": "Asmeninis biudžetas: kaip sudaryti planą",
            "meta_description": (
                "Kaip sudaryti asmeninį biudžetą pagal realias pajamas ir išlaidas, "
                "palyginti planą su faktu ir tikslinti kitą mėnesį."
            ),
            "prefix": BUDGET_PREFIX,
            "link": (
                "\n\nSkirtingus planavimo būdus palyginame straipsnyje "
                "[Biudžeto planavimo metodai](/straipsniai/biudzeto-planavimo-metodai/)."
            ),
        },
        "islaidu-sekimas": {
            "meta_title": "Išlaidų sekimo programėlė: praktinis vadovas",
            "meta_description": (
                "Išlaidų sekimo programėlė, Excel ar banko įrankis? Praktinis vadovas, "
                "kaip rinkti operacijas, tvarkyti kategorijas ir atlikti mėnesio peržiūrą."
            ),
            "prefix": "",
            "link": (
                "\n\nJei pradedate nuo banko failo, tęskite su "
                "[banko išrašo analizės vadovu](/straipsniai/banko-israso-analize/) "
                "arba peržiūrėkite [MoneyCompass finansų programėlę](/finansu-valdymo-programele/)."
            ),
        },
    }

    for slug, values in updates.items():
        article = Article.objects.filter(slug=slug).first()
        if not article:
            continue
        body = article.body
        if values["prefix"] and values["prefix"].strip() not in body:
            body = values["prefix"] + body
        if values["link"].strip() not in body:
            body = body + values["link"]
        article.body = body
        article.meta_title = values["meta_title"]
        article.meta_description = values["meta_description"]
        article.updated_at = now
        article.save(
            update_fields=[
                "body",
                "meta_title",
                "meta_description",
                "updated_at",
            ]
        )

    rows = [
        {
            "slug": "banko-israso-analize",
            "title": "Banko išrašo analizė: 7 žingsniai aiškesniam finansų vaizdui",
            "meta_title": "Banko išrašo analizė: praktinis vadovas",
            "meta_description": (
                "Kaip analizuoti banko išrašą: atskirti pervedimus, suskirstyti išlaidas, "
                "rasti reguliarius mokėjimus ir padaryti naudingas išvadas."
            ),
            "excerpt": (
                "Praktinis banko išrašo analizės procesas nuo pilno mėnesio operacijų iki "
                "aiškių kategorijų, palyginimų ir kito mėnesio sprendimų."
            ),
            "body": BANK_STATEMENT,
        },
        {
            "slug": "biudzeto-planavimo-metodai",
            "title": "Biudžeto planavimo metodai: kurį pasirinkti?",
            "meta_title": "Biudžeto planavimo metodai: palyginimas",
            "meta_description": (
                "Palyginkite kategorijų, nulinio biudžeto, procentinių grupių, savaitinių "
                "ribų ir kintamų pajamų planavimo metodus."
            ),
            "excerpt": (
                "Penki biudžeto planavimo metodai, jų privalumai, ribos ir aiškus būdas "
                "pasirinkti pagal savo pajamas bei norimą detalumą."
            ),
            "body": BUDGET_METHODS,
        },
        {
            "slug": "menesio-finansu-perziura",
            "title": "Mėnesio finansų peržiūra: ką patikrinti per 30 minučių",
            "meta_title": "Mėnesio finansų peržiūra: kontrolinis sąrašas",
            "meta_description": (
                "30 minučių mėnesio finansų peržiūra: pajamos, išlaidos, kategorijos, "
                "reguliarūs mokėjimai, turtas, tikslai ir kitas planas."
            ),
            "excerpt": (
                "Nuoseklus mėnesio finansų peržiūros kontrolinis sąrašas, padedantis "
                "paaiškinti pokyčius ir parengti realesnį kitą biudžetą."
            ),
            "body": MONTHLY_REVIEW,
        },
    ]

    for row in rows:
        Article.objects.update_or_create(
            slug=row["slug"],
            defaults={
                "language": "lt",
                "title": row["title"],
                "meta_title": row["meta_title"],
                "meta_description": row["meta_description"],
                "excerpt": row["excerpt"],
                "body": row["body"],
                "author_name": "MoneyCompass komanda",
                "status": "published",
                "published_at": now,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("blog", "0005_strengthen_expense_tracking_search_intent")]
    operations = [migrations.RunPython(publish_cluster, migrations.RunPython.noop)]
