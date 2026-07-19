from django.db import migrations
from django.utils import timezone


PILLAR = """Asmeninių finansų valdymas prasideda nuo aiškaus atsakymo į du klausimus: kiek pinigų gaunate ir kur jie iškeliauja. Tik tada verta kurti biudžetą, vertinti turtą ar planuoti tikslus. Šis vadovas padės susikurti paprastą sistemą, kurią galima palaikyti ilgiau nei vieną mėnesį.

## Kas yra asmeninių finansų valdymas?

Asmeninių finansų valdymas – tai pajamų, išlaidų, turto, įsipareigojimų ir tikslų stebėjimas bei planavimas. Tai nėra vien taupymas. Svarbiausia matyti visą vaizdą ir priimti sprendimus remiantis savo duomenimis.

[Lietuvos bankas](https://www.lb.lt/lt/asmeniniai-finansai) asmeninį biudžetą apibrėžia kaip pajamų ir išlaidų planą ir siūlo pradžioje bent mėnesį žymėtis realias pajamas bei išlaidas. Toks stebėjimo laikotarpis padeda planą kurti pagal tikrovę, o ne spėjimus.

## 1. Surinkite pajamas ir išlaidas į vieną vietą

Pradėkite nuo paskutinio pilno mėnesio. Surinkite banko išrašus, grynųjų pinigų įrašus ir reguliarias pajamas. Jeigu naudojate kelias sąskaitas, vertinkite jas kartu. Vienos sąskaitos likutis neparodo viso finansinio vaizdo.

Svarbu ne kiekvieną operaciją iškart įvertinti, o užfiksuoti. Praktinį procesą išsamiau aprašome [išlaidų sekimo vadove](/straipsniai/islaidu-sekimas/).

## 2. Susikurkite prasmingas išlaidų kategorijas

Pradžiai pakanka kelių kategorijų: būstas, maistas, transportas, sveikata, laisvalaikis, prenumeratos ir kitos išlaidos. Per daug smulkių kategorijų apsunkina peržiūrą, o per plačios kategorijos neatsako, kas iš tiesų pasikeitė.

- Atskirkite reguliarias ir kintamas išlaidas.
- Pažymėkite metinius ar sezoninius mokėjimus.
- Turėkite atskirą kategoriją operacijoms, kurias dar reikia patikrinti.

## 3. Sudarykite planą pagal realius duomenis

Kai turite bent vieno mėnesio duomenis, sudarykite kito mėnesio planą. Įrašykite tikėtinas pajamas, reguliarius mokėjimus, kintamų išlaidų orientyrus ir sumas tikslams. [Asmeninio biudžeto vadove](/straipsniai/asmeninis-biudzetas/) rasite nuoseklų planavimo procesą ir paprastą pavyzdį.

Biudžetas nėra pažadas kiekvieną kategoriją įvykdyti centų tikslumu. Tai palyginimo taškas. Jei faktinės išlaidos skiriasi, svarbu suprasti priežastį ir kitą planą padaryti tikslesnį.

## 4. Įtraukite turtą, įsipareigojimus ir tikslus

Mėnesio išlaidos rodo pinigų srautą, tačiau ne visą padėtį. Bendram vaizdui prireiks turto, santaupų, investicijų ir įsipareigojimų. Vertes atnaujinkite vienodu periodiškumu, pavyzdžiui, mėnesio pabaigoje.

Finansinis tikslas turėtų turėti pavadinimą, norimą sumą ir terminą. Progreso stebėjimas parodo kryptį, tačiau MoneyCompass nepateikia individualių rekomendacijų, kokį tikslą ar finansinį produktą pasirinkti.

## 5. Įveskite trumpą peržiūros rutiną

Kartą per savaitę patikrinkite naujas operacijas ir neaiškius įrašus. Kartą per mėnesį palyginkite planą su rezultatu, įvertinkite kategorijų pokyčius ir atnaujinkite turto bei tikslų duomenis.

Sistema turi taupyti laiką, o ne tapti antru darbu. Jeigu išlaidas registruojate, bet niekada neperžiūrite suvestinės, duomenys dar nepadeda priimti sprendimų.

## Kaip čia padeda MoneyCompass?

MoneyCompass leidžia rankiniu būdu importuoti CSV arba Excel banko išrašus, suskirstyti operacijas į kategorijas ir vienoje vietoje matyti išlaidas, turtą, investicijas bei tikslus. Programa neprisijungia prie banko ir neprašo banko prisijungimo duomenų.

Tai finansų stebėjimo ir planavimo įrankis, o ne finansų patarėjas. Jūsų duomenys padeda geriau suprasti situaciją, tačiau individualius sprendimus priimate jūs.

## Šaltiniai

- [Lietuvos bankas: asmeniniai finansai](https://www.lb.lt/lt/asmeniniai-finansai)
- [Lietuvos bankas: finansinis raštingumas](https://www.lb.lt/lt/finansinis-rastingumas)"""


TRACKING = """Išlaidų sekimas padeda atsakyti į konkretų klausimą: kur per mėnesį išėjo pinigai? Tam nereikia kasdien pildyti sudėtingos lentelės. Reikia patikimo duomenų šaltinio, aiškių kategorijų ir reguliarios, trumpos peržiūros.

## Kada išlaidų sekimas iš tiesų naudingas?

Išlaidų sekimas ypač naudingas, kai mėnesio pabaigoje sunku paaiškinti sąskaitos likutį, kai keičiasi pajamos arba kai norite įvertinti naują finansinį tikslą. Stebėjimas nėra tikslas savaime. Jo paskirtis – parodyti pasikartojančius sprendimus.

[Lietuvos bankas](https://www.lb.lt/lt/asmeniniai-finansai) rekomenduoja pradžioje ne trumpiau kaip vieną mėnesį žymėtis pajamas ir išlaidas. Vienas pilnas mėnuo apima daugumą reguliarių mokėjimų ir suteikia geresnį pagrindą planui.

## 1. Pasirinkite vieną duomenų surinkimo būdą

Galite naudoti užrašus, skaičiuoklę, banko įrankį arba finansų programėlę. Svarbiausia, kad duomenys nebūtų išskaidyti keliose nesusijusiose vietose. Jei atsiskaitote keliomis kortelėmis, įtraukite visas sąskaitas.

MoneyCompass atveju banko išrašas importuojamas rankiniu būdu iš CSV arba Excel failo. Tai leidžia analizuoti operacijas nesuteikiant programai banko prisijungimo duomenų.

## 2. Pradėkite nuo nedidelio kategorijų sąrašo

Kategorijos turi padėti palyginti laikotarpius. Pradžiai naudokite 6–10 aiškių grupių, o smulkinkite tik tada, kai atsiranda konkretus klausimas.

- Būstas ir komunalinės paslaugos
- Maistas ir kasdienės prekės
- Transportas
- Sveikata
- Laisvalaikis ir prenumeratos
- Kitos arba dar nepatikrintos išlaidos

Pardavėjo pavadinimas ne visada tiksliai parodo pirkinio paskirtį, todėl neaiškias operacijas geriau pažymėti peržiūrai, o ne priskirti atsitiktinai.

## 3. Atskirai pažymėkite reguliarias ir vienkartines išlaidas

Reguliarūs mokėjimai kartojasi kas mėnesį ar kitu nustatytu periodu. Vienkartinis remontas ar kelionė neturėtų klaidinti vertinant įprasto mėnesio išlaidas. Atskyrimas leidžia pastebėti, ar pasikeitė kasdieniai įpročiai, ar tiesiog įvyko retas pirkimas.

## 4. Peržiūrėkite duomenis tuo pačiu metu

Trumpa savaitinė peržiūra padeda sutvarkyti neaiškias operacijas, kol dar prisimenate kontekstą. Mėnesio pabaigoje palyginkite kategorijų sumas ir bendrą pinigų srautą su ankstesniu laikotarpiu.

Paklauskite:

- Kuri kategorija pasikeitė labiausiai?
- Ar pokytį sukėlė vienkartinis įvykis?
- Ar yra pamirštų prenumeratų ar pasikartojančių mokesčių?
- Ar mėnesio rezultatas atitiko planą?

## 5. Paverskite stebėjimą kitu planu

Vien tik operacijų sąrašas elgesio nekeičia. Naudingiausia peržiūros išvada yra nedidelis kito mėnesio pakeitimas: tikslesnis kategorijos orientyras, atnaujintas tikslas arba aiškesnis sezoninės išlaidos planas.

Kaip duomenis paversti mėnesio planu, paaiškiname [asmeninio biudžeto vadove](/straipsniai/asmeninis-biudzetas/). Platesnį sistemos vaizdą rasite [asmeninių finansų valdymo vadove](/straipsniai/asmeniniu-finansu-valdymas/).

## Dažniausios išlaidų sekimo klaidos

**Per daug kategorijų.** Sistema tampa lėta, o skirtumai tarp kategorijų – neaiškūs.

**Praleistos grynųjų operacijos.** Kortelių išrašas neapima visų mokėjimų, todėl grynuosius reikia įrašyti atskirai.

**Vertinimas po kelių dienų.** Viena brangesnė diena dar nėra tendencija. Išvadas geriau daryti iš pilno laikotarpio.

**Duomenys be peržiūros.** Jeigu skaičiai kaupiami, bet nepalyginami, išlaidų sekimas neduoda visos naudos.

## Išlaidų sekimas su MoneyCompass

MoneyCompass suskirsto importuotas operacijas į jūsų pasirenkamas kategorijas ir pateikia suvestines. Duomenis importuojate patys, todėl nereikia tiesioginio banko ryšio. MoneyCompass yra stebėjimo įrankis ir neteikia individualių finansinių rekomendacijų.

## Šaltiniai

- [Lietuvos bankas: asmeniniai finansai](https://www.lb.lt/lt/asmeniniai-finansai)
- [Lietuvos bankas: finansinis raštingumas](https://www.lb.lt/lt/finansinis-rastingumas)"""


BUDGET = """Asmeninis biudžetas yra pajamų ir išlaidų planas pasirinktam laikotarpiui, dažniausiai mėnesiui. Geras planas neapsiriboja draudimais: jis parodo, kiek pinigų reikės reguliariems mokėjimams, kiek lieka kintamoms išlaidoms ir kaip juda jūsų tikslai.

## Kam reikalingas asmeninis biudžetas?

Biudžetas suteikia palyginimo tašką. Be plano matote tik tai, kas jau įvyko. Turėdami planą galite palyginti numatytas ir faktines sumas, suprasti skirtumus ir tikslinti kitą mėnesį.

[Lietuvos bankas](https://www.lb.lt/lt/asmeniniai-finansai) asmeninį biudžetą apibrėžia kaip pajamų ir išlaidų planą. Oficialiame vadove pabrėžiama, kad planuojant svarbu tiksliai nurodyti pajamas ir išlaidas, o pradžioje bent mėnesį jas stebėti.

## 1. Užrašykite patikimas mėnesio pajamas

Įtraukite pajamas, kurias pagrįstai tikitės gauti per planuojamą mėnesį. Jei pajamos kinta, atskirkite jau patvirtintas sumas nuo neapibrėžtų. Tokiu atveju planą verta atnaujinti, kai turite naujos informacijos.

## 2. Pirmiausia įrašykite reguliarius įsipareigojimus

Būsto, komunalinių paslaugų, draudimo, ryšio ir kitų sutarčių mokėjimai dažnai turi aiškią datą. Metinius mokėjimus galima padalyti į mėnesio dalis, kad jie neužkluptų netikėtai.

- Mėnesiniai mokėjimai
- Ketvirtiniai ir metiniai mokėjimai
- Sezoninės išlaidos
- Žinomi vienkartiniai pirkiniai

## 3. Kintamoms išlaidoms naudokite orientyrus

Maisto, transporto ir laisvalaikio sumos retai kartojasi tiksliai. Orientyrą nustatykite pagal ankstesnių mėnesių duomenis. Jei jų dar neturite, vieną mėnesį atlikite [išlaidų sekimą](/straipsniai/islaidu-sekimas/) ir tik tada nustatykite realistiškesnes sumas.

Universali procentinė taisyklė nebūtinai tinka skirtingoms pajamoms, šeimos dydžiui ar gyvenamajai vietai. MoneyCompass nenurodo, kokią pajamų dalį privalote skirti konkrečiai kategorijai.

## 4. Įtraukite finansinius tikslus

Tikslą aprašykite konkrečiai: pavadinimas, norima suma ir terminas. Mėnesio plane matysis, kokią sumą planuojate jam skirti. Jei realus mėnuo skiriasi nuo plano, tikslą arba terminą galima atnaujinti pagal savo aplinkybes.

## 5. Palikite vietos nereguliarioms išlaidoms

Ne kiekviena išlaida yra netikėta vien todėl, kad pasitaiko retai. Automobilio priežiūra, dovanos ar sezoniniai mokesčiai dažnai pasikartoja. Ankstesnių metų įrašai padeda juos įtraukti į planą iš anksto.

## 6. Mėnesio pabaigoje palyginkite planą su faktu

Palyginkite kiekvienos kategorijos planuotą ir faktinę sumą. Didžiausias skirtumas nebūtinai yra problema – jis yra signalas pasidomėti priežastimi.

Paprastas pavyzdys:

- Planuotos mėnesio pajamos: 1 800 Eur
- Reguliarūs mokėjimai: 900 Eur
- Kintamų išlaidų orientyras: 600 Eur
- Tikslams numatyta suma: 200 Eur
- Lanksti likusi suma: 100 Eur

Tai tik struktūros pavyzdys, o ne rekomenduojamas paskirstymas. Jūsų biudžetas turi remtis jūsų pajamomis, įsipareigojimais ir prioritetais.

## Kaip palaikyti biudžetą ilgiau nei mėnesį?

Naudokite tą pačią kategorijų sistemą bent kelis laikotarpius, nekeiskite visko dėl vieno nukrypimo ir peržiūrai pasirinkite pastovų laiką. Platesnę sistemą – nuo išlaidų iki turto ir tikslų – aprašome [asmeninių finansų valdymo vadove](/straipsniai/asmeniniu-finansu-valdymas/).

## Asmeninis biudžetas su MoneyCompass

MoneyCompass leidžia importuoti banko išrašus iš CSV arba Excel failų, matyti faktines išlaidas pagal kategorijas ir stebėti tikslus. Programa neprisijungia prie banko, o jūsų biudžeto sprendimų nepriima už jus.

## Šaltiniai

- [Lietuvos bankas: asmeniniai finansai](https://www.lb.lt/lt/asmeniniai-finansai)
- [Lietuvos bankas: finansinis raštingumas](https://www.lb.lt/lt/finansinis-rastingumas)"""


PILLAR_EXTRA = """

## Pinigų srautas ir bendras turtas nėra tas pats

Pinigų srautas parodo, kiek per laikotarpį gavote ir išleidote. Bendras turto vaizdas apima tai, ką turite, ir tai, ką esate įsipareigoję sumokėti. Galite turėti teigiamą mėnesio rezultatą, tačiau tuo pat metu turėti ilgalaikių įsipareigojimų. Galima ir priešinga situacija: vieną mėnesį išleisti daugiau dėl suplanuoto didelio pirkinio, nors bendras turto vaizdas išlieka stabilus.

Todėl asmeninių finansų valdymas turėtų atsakyti į du atskirus klausimus:

- Kaip pasikeitė šio mėnesio pajamos ir išlaidos?
- Kaip pasikeitė turto, santaupų ir įsipareigojimų vaizdas?

Šių rodiklių nereikia sujungti į vieną neaiškų skaičių. Juos verta stebėti greta, nes jie paaiškina skirtingas finansinės situacijos dalis.

## Kaip tvarkyti pervedimus tarp savo sąskaitų?

Pervedimas iš vienos savo sąskaitos į kitą nėra naujos pajamos ir nėra vartojimo išlaida. Jei abi operacijos įtraukiamos kaip atskiros pajamos ir išlaidos, mėnesio suvestinė išsipučia. Tą patį reikia prisiminti perkeliant pinigus į taupomąją ar investicinę sąskaitą.

Grąžinimai taip pat reikalauja nuoseklumo. Galite juos susieti su pradine kategorija arba rodyti atskirai, tačiau pasirinktas metodas turėtų nesikeisti kiekvieną mėnesį. Nuoseklūs duomenys leidžia prasmingiau lyginti laikotarpius.

## Kokią finansų programėlę pasirinkti?

Finansų programėlė turėtų atitikti jūsų darbo būdą. Prieš pasirinkdami įrankį įvertinkite, kokius duomenis norite matyti, kaip jie patenka į sistemą ir ar galėsite juos eksportuoti arba ištrinti.

Naudingi vertinimo klausimai:

- Ar įrankis skirtas asmeniniams, o ne įmonės finansams?
- Ar palaikomos jums reikalingos banko išrašų formos?
- Ar galima kurti savo išlaidų kategorijas?
- Ar matysite ne tik išlaidas, bet ir turtą bei tikslus?
- Ar aiškiai paaiškinta, kaip saugomi ir šalinami duomenys?
- Ar įrankis prašo tiesioginio banko prisijungimo, ar leidžia importuoti išrašą patiems?

MoneyCompass pasirinko rankinį importą. Tai reiškia papildomą veiksmą vartotojui, tačiau nereikia suteikti programai banko prisijungimo duomenų ar nuolatinės prieigos prie sąskaitos.

## Paprastas 30 dienų pradžios planas

**Pirma savaitė.** Surinkite sąskaitas ir importuokite turimas operacijas. Sukurkite nedidelį pagrindinių kategorijų sąrašą.

**Antra savaitė.** Patikrinkite neaiškius pardavėjų pavadinimus, pervedimus tarp savo sąskaitų ir grynųjų mokėjimus.

**Trečia savaitė.** Peržiūrėkite didžiausias kategorijas ir reguliarius mokėjimus. Dar nekeiskite sistemos vien dėl kelių neįprastų operacijų.

**Mėnesio pabaiga.** Suskaičiuokite faktines pajamas bei išlaidas, atnaujinkite turtą ir pagal rezultatus sudarykite kito mėnesio planą.

Po pirmo mėnesio turėsite pradinį atskaitos tašką. Po kelių mėnesių galėsite lyginti laikotarpius ir atskirti sezoninius pokyčius nuo pasikartojančių įpročių.

## Kada sistema tampa per sudėtinga?

Jei kiekvienai operacijai sutvarkyti reikia daug sprendimų, kategorijų tikriausiai per daug. Jei peržiūra trunka ilgiau, nei suteikia naudos, sumažinkite stebimų rodiklių skaičių. Gera sistema turi pateikti aiškų atsakymą, o ne gaminti kuo daugiau diagramų.

Asmeninių finansų valdymas nėra vienkartinis projektas. Tai trumpas ciklas: surinkti duomenis, peržiūrėti rezultatą, pakoreguoti planą ir pakartoti. Kuo paprastesnis ciklas, tuo didesnė tikimybė, kad jo laikysitės."""

TRACKING_EXTRA = """

## Kaip sekti grynųjų pinigų išlaidas?

Banko išrašas neparodo, kam panaudojote iš bankomato išsiimtus pinigus. Jei grynieji sudaro pastebimą jūsų mokėjimų dalį, vien išėmimo operacija nėra pakankamai informatyvi.

Galite pasirinkti vieną iš dviejų paprastų metodų. Pirmasis – visą išimtą sumą priskirti grynųjų kategorijai. Jis greitas, bet neatskleidžia paskirties. Antrasis – svarbesnius grynųjų pirkinius įrašyti atskirai, o likutį palikti bendroje kategorijoje. Svarbiausia pasirinkto metodo nekeisti kiekvieną savaitę.

## Kaip vertinti bendras ir asmenines išlaidas?

Jei išlaidas dalijatės su partneriu ar šeima, iš anksto sutarkite, ką norite matyti. Vieniems pakanka bendros namų ūkio sumos. Kitiems svarbu atskirti bendras išlaidas nuo asmeninių pirkinių.

Pasirinkite aiškią taisyklę:

- Bendras išlaidas žymėkite ta pačia kategorija arba žyma.
- Pervedimų tarp partnerių neskaičiuokite antrą kartą kaip vartojimo išlaidų.
- Susitarkite, ar kompensuota išlaida mažina pradinę kategoriją.

Tikslas nėra kontroliuoti kito žmogaus pirkinius. Tikslas – išvengti dvigubo skaičiavimo ir turėti abiem suprantamą vaizdą.

## Ką lyginti mėnesio pabaigoje?

Bendra suma naudinga, tačiau viena nepaaiškina pokyčio. Išlaidų sekimo peržiūroje palyginkite:

- Bendras išlaidas su praėjusiu mėnesiu.
- Didžiausias kategorijas ir jų dalį bendrose išlaidose.
- Reguliarius mokėjimus bei naujas prenumeratas.
- Vienkartines išlaidas, kurios kitą mėnesį neturėtų kartotis.
- Operacijas, kurioms vis dar nepriskirta kategorija.

Sezoninius laikotarpius geriau lyginti ir su atitinkamu ankstesnių metų laikotarpiu, jei turite duomenų. Gruodžio ir sausio skirtumas nebūtinai reiškia naują ilgalaikę tendenciją.

## Ar reikia sekti kiekvieną centą visą laiką?

Ne kiekvienam reikia vienodo detalumo. Pradžioje išsamesnis išlaidų sekimas padeda suprasti situaciją. Vėliau galite palikti tik tas kategorijas ir peržiūras, kurios duoda naudingą informaciją.

Detalumą verta padidinti, kai pasikeičia pajamos, atsiranda naujas įsipareigojimas, planuojamas didesnis tikslas arba sąskaitos rezultatas tampa neaiškus. Stabiliu laikotarpiu gali pakakti mėnesinės išrašo peržiūros.

## Kaip atpažinti kokybišką išlaidų sekimo programėlę?

Išlaidų sekimo programėlė turėtų greitai parodyti kategorijų sumas ir leisti pataisyti neteisingai priskirtą operaciją. Taip pat svarbu suprasti duomenų importo, saugojimo ir šalinimo tvarką.

Patikrinkite, ar galite:

- Importuoti realiai naudojamo banko išrašo formatą.
- Sukurti savo kategorijas ir jas keisti.
- Atskirti pervedimus nuo tikrų pajamų bei išlaidų.
- Peržiūrėti ankstesnius laikotarpius.
- Pašalinti įkeltus duomenis ir paskyrą.

## Keturių savaičių išlaidų sekimo eksperimentas

Pirmą savaitę tik surinkite operacijas. Antrą savaitę sutvarkykite kategorijas. Trečią savaitę pasižymėkite reguliarius ir vienkartinius mokėjimus. Ketvirtą savaitę atlikite pilną mėnesio peržiūrą ir užrašykite dvi išvadas.

Toks ribotas eksperimentas padeda įvertinti procesą be pažado viską registruoti amžinai. Jei išvados naudingos, palikite paprasčiausią veikiančią versiją kitam mėnesiui."""

BUDGET_EXTRA = """

## Kuo biudžeto planavimas skiriasi nuo išlaidų sekimo?

Išlaidų sekimas aprašo tai, kas jau įvyko. Biudžeto planavimas numato, kaip norite paskirstyti būsimą laikotarpį. Šie procesai papildo vienas kitą: ankstesni duomenys padeda sukurti realesnį planą, o planas suteikia pagrindą mėnesio rezultatui įvertinti.

Jei dar neturite istorinių duomenų, pirmas biudžetas bus apytikslis. Tai normalu. Po kiekvieno mėnesio orientyrus galima patikslinti.

## Kaip planuoti biudžetą, kai pajamos kinta?

Kintamų pajamų atveju atskirkite patvirtintas pajamas nuo galimų. Reguliarius įsipareigojimus planuokite pagal sumą, kurią pagrįstai tikitės gauti, o ne pagal geriausią ankstesnį mėnesį.

Galite naudoti kelis scenarijus:

- Bazinis planas remiasi patvirtintomis pajamomis.
- Didesnių pajamų scenarijus nurodo, kam skirtumėte papildomą sumą.
- Mažesnių pajamų scenarijus padeda iš anksto matyti, kurias kintamas išlaidas būtų galima atidėti.

Tai nėra prognozė ar rekomendacija. Scenarijai tiesiog parodo, kaip pasikeistų jūsų pačių planas esant kitai pajamų sumai.

## Asmeninis ir šeimos biudžetas

Šeimos biudžetui reikia ne tik skaičių, bet ir bendrų taisyklių. Nuspręskite, kurios pajamos bei išlaidos yra bendros, kurios lieka asmeninės ir kaip registruosite vieno žmogaus apmokėtą bendrą pirkinį.

Naudinga sutarti dėl trijų dalykų:

- Kokias kategorijas peržiūrite kartu?
- Kaip dažnai aptariate rezultatą?
- Kokio dydžio ar tipo pirkinius planuojate iš anksto?

Vienas bendras metodas sumažina dvigubą skaičiavimą. Tačiau šeimos biudžetas neturi panaikinti asmeninio privatumo – kategorijų detalumą nusistatykite tarpusavio susitarimu.

## Kaip planuoti nereguliarias išlaidas?

Peržiūrėkite ankstesnių metų įrašus ir kalendorių. Draudimas, automobilio priežiūra, mokyklos pradžia, šventės ar atostogos dažnai nėra netikėtos, nors nemokamos kiekvieną mėnesį.

Metinę numatomą sumą galima padalyti į mėnesio dalis ir plane žymėti kaip atskirą kategoriją. Faktinis mokėjimas įvyks vėliau, tačiau planas iš anksto parodys jo poveikį.

## Ką daryti, kai faktas skiriasi nuo plano?

Pirmiausia nustatykite skirtumo tipą. Ar pasikeitė kaina? Ar atsirado vienkartinis įvykis? Ar pradinė suma buvo spėjimas be ankstesnių duomenų? Atsakymas nurodo, ar reikia keisti kitą planą.

Neskubėkite mažinti visų kategorijų vienodai. Tikslesnis sprendimas gali būti atnaujinti vieną nerealistišką orientyrą, pridėti sezoninę kategoriją arba pataisyti neteisingai priskirtas operacijas.

## Mėnesio biudžeto uždarymo kontrolinis sąrašas

- Patikrinkite, ar įtrauktos visos sąskaitos ir grynųjų mokėjimai.
- Sutvarkykite neaiškias operacijas ir pervedimus tarp savo sąskaitų.
- Palyginkite planą su faktu pagal kategorijas.
- Pažymėkite vienkartinius bei sezoninius skirtumus.
- Atnaujinkite kito mėnesio pajamas, įsipareigojimus ir tikslus.
- Užrašykite vieną ar du pakeitimus, kuriuos norite išbandyti.

## Biudžeto programėlė ar skaičiuoklė?

Skaičiuoklė suteikia daug laisvės, tačiau struktūrą ir formules turite prižiūrėti patys. Biudžeto programėlė gali greičiau pateikti kategorijų suvestines, tačiau svarbu įvertinti importo būdą, privatumą ir galimybę eksportuoti duomenis.

Rinkitės ne pagal funkcijų skaičių, o pagal tai, ar įrankį realiai naudosite kiekvieno mėnesio peržiūrai. Paprasta ir nuosekli sistema yra vertingesnė už sudėtingą planą, kurio neatnaujinate."""

PILLAR = PILLAR.replace("\n\n## Šaltiniai", PILLAR_EXTRA + "\n\n## Šaltiniai")
TRACKING = TRACKING.replace("\n\n## Šaltiniai", TRACKING_EXTRA + "\n\n## Šaltiniai")
BUDGET = BUDGET.replace("\n\n## Šaltiniai", BUDGET_EXTRA + "\n\n## Šaltiniai")

PILLAR = PILLAR.replace("\n\n## Šaltiniai", """

## Kaip suprasti pirmąją finansų suvestinę?

Pirmoje suvestinėje ieškokite ne idealaus rezultato, o paaiškinimų. Pradėkite nuo trijų didžiausių išlaidų kategorijų, reguliarių mokėjimų ir mėnesio pajamų bei išlaidų skirtumo. Tada patikrinkite, ar suvestinę iškraipo pervedimai, grąžinimai arba vienkartiniai pirkiniai.

Jeigu viena kategorija atrodo neįprastai didelė, atverkite jos operacijas. Gali paaiškėti, kad joje yra kelių tipų pirkimai arba neteisingai priskirtas pervedimas. Tik išvalius duomenis verta lyginti mėnesius.

## Kokius rodiklius verta stebėti pradžioje?

Pradžioje pakanka nedidelio rodiklių rinkinio:

- Mėnesio pajamos ir bendros išlaidos.
- Didžiausios išlaidų kategorijos.
- Reguliarių mokėjimų suma.
- Turto ir įsipareigojimų pokytis.
- Pasirinktų finansinių tikslų progresas.

Vėliau galite pridėti daugiau detalių, jei jos atsako į konkretų klausimą. Rodiklis, kuris nekeičia jokio sprendimo ir nėra peržiūrimas, greičiausiai nėra būtinas.

## Ar asmeninių finansų programėlė pakeičia finansų specialistą?

Ne. Asmeninių finansų programėlė padeda surinkti, suskirstyti ir parodyti jūsų duomenis. Ji gali palengvinti pasiruošimą pokalbiui su kvalifikuotu specialistu, tačiau vien suvestinė neįvertina visų asmeninių aplinkybių, teisinių reikalavimų ar konkretaus finansinio produkto rizikos.

MoneyCompass sąmoningai pozicionuojamas kaip finansų stebėjimo įrankis. Straipsniai yra bendro edukacinio pobūdžio ir nepakeičia individualios konsultacijos.

## Ką daryti toliau?

Jei dar neturite duomenų, pradėkite nuo vieno pilno mėnesio išrašo. Jei duomenis jau sekate, susikurkite kito mėnesio planą ir vieną pastovų peržiūros laiką. Pirmasis tikslas nėra tobula sistema – tai sistema, kuri po mėnesio vis dar naudojama.
""" + "\n\n## Šaltiniai")

TRACKING = TRACKING.replace("\n\n## Šaltiniai", """

## Pavyzdys: nuo banko išrašo iki naudingos išvados

Tarkime, banko išraše matote 70 operacijų. Pirmiausia atskiriate pervedimus tarp savo sąskaitų ir grąžinimus. Likusias operacijas priskiriate pagrindinėms kategorijoms. Mėnesio suvestinėje paaiškėja, kad laisvalaikio kategorija padidėjo, tačiau didžiąją pokyčio dalį sudaro vienas iš anksto planuotas renginys.

Naudinga išvada nėra „per daug išleidau“. Tikslesnė išvada: įprastos laisvalaikio išlaidos beveik nepasikeitė, o bendrą sumą padidino vienkartinis įvykis. Kito mėnesio kasdienio orientyro dėl to keisti nebūtina, tačiau panašų renginį galima įtraukti į būsimą planą atskirai.

## Ką daryti su neteisingomis arba dubliuotomis operacijomis?

Importavę išrašą patikrinkite laikotarpį ir sąskaitą. Pakartotinai importuotas tas pats failas gali sukurti dublikatus, jei įrankis jų neatpažįsta. Prieš trindami įrašus įsitikinkite, kad sutampa data, suma ir operacijos aprašymas.

Jeigu pardavėjo pavadinimas neaiškus, operaciją laikinai palikite kategorijoje „Patikrinti“. Neteisinga kategorija gali iškraipyti išvadą labiau nei keli neklasifikuoti įrašai.

## Privatumas sekant išlaidas

Banko išraše gali būti jautri informacija apie pirkinius, pajamas ir įpročius. Prieš pasirinkdami įrankį perskaitykite privatumo politiką, duomenų saugojimo paaiškinimą ir paskyros ištrynimo procesą. Nesiųskite išrašų neaiškioms paslaugoms ir neskelbkite jų viešai.

MoneyCompass naudoja rankinį failo importą ir neprašo banko slaptažodžio. Vis tiek svarbu saugoti savo paskyrą, naudoti unikalų slaptažodį ir peržiūrėti, kokius failus įkeliate.

## Trumpas atsakymas: kaip sekti išlaidas?

Surinkite visas mėnesio operacijas, pašalinkite dvigubą pervedimų skaičiavimą, naudokite kelias aiškias kategorijas ir kartą per mėnesį palyginkite rezultatą. Tada pasirinkite vieną konkretų kito mėnesio pakeitimą. Būtent peržiūra, o ne vien duomenų kaupimas, paverčia išlaidų sekimą naudingu.
""" + "\n\n## Šaltiniai")

BUDGET = BUDGET.replace("\n\n## Šaltiniai", """

## Pavyzdys: kaip tikslinti biudžetą po pirmo mėnesio

Tarkime, maistui suplanavote 350 Eur, o faktinė suma buvo 410 Eur. Prieš mažindami kitą planą patikrinkite operacijas. Galbūt 45 Eur sudarė svečių vakarienė, kurios kitą mėnesį nebus. Tuomet įprastas išlaidų lygis buvo artimesnis planui nei rodo bendra kategorijos suma.

Kitas pavyzdys – komunaliniai mokėjimai. Jei jie padidėjo dėl sezono, kitą mėnesį verta naudoti naujesnį orientyrą. Skirtumo priežastis padeda nuspręsti, ar keisti planą, ar tik pažymėti vienkartinį įvykį.

## Ar būtina planuoti kiekvieną eurą?

Ne. Vieniems patinka labai detalus planas, kitiems pakanka reguliarių mokėjimų, kelių kintamų kategorijų ir tikslų. Detalumas turi būti toks, kad padėtų priimti sprendimus ir nereikalautų neproporcingai daug laiko.

Jei viena plati kategorija nuolat kelia klausimų, ją suskaidykite. Jei kelių kategorijų niekada neperžiūrite atskirai, jas sujunkite. Biudžeto struktūra gali keistis kartu su gyvenimo aplinkybėmis.

## Kaip vertinti biudžeto sėkmę?

Sėkmė nėra vien faktas, kad kiekviena kategorija neviršijo plano. Vertinkite, ar:

- Įtraukėte visas svarbias pajamas ir išlaidas.
- Suprantate didžiausių skirtumų priežastis.
- Reguliarūs mokėjimai neužklupo netikėtai.
- Tikslų progresas atnaujintas realiais duomenimis.
- Kito mėnesio planas tapo tikslesnis.

Biudžetas yra grįžtamojo ryšio sistema. Kiekvienas mėnuo pateikia naujų duomenų, o šie padeda patikslinti kitą planą.

## Trumpas atsakymas: kaip sudaryti asmeninį biudžetą?

Užrašykite patikimas pajamas, reguliarius įsipareigojimus, kintamų išlaidų orientyrus, nereguliarius mokėjimus ir tikslus. Mėnesio pabaigoje palyginkite planą su faktinėmis operacijomis, paaiškinkite didžiausius skirtumus ir atnaujinkite kitą mėnesį. Tai paprastesnis ir patikimesnis procesas nei vien universali procentinė formulė.
""" + "\n\n## Šaltiniai")


def upsert(apps, schema_editor):
    Article = apps.get_model("blog", "Article")
    now = timezone.now()
    rows = [
        ("asmeniniu-finansu-valdymas", "Asmeninių finansų valdymas: kaip pradėti nuo nulio", "Asmeninių finansų valdymas: kaip pradėti", "Sužinokite, kaip valdyti asmeninius finansus: sekti išlaidas, planuoti biudžetą ir vienoje vietoje matyti savo finansinį vaizdą.", "Nuoseklus asmeninių finansų valdymo planas: nuo pajamų ir išlaidų iki turto, tikslų ir mėnesinės peržiūros.", PILLAR),
        ("islaidu-sekimas", "Išlaidų sekimas: kaip pradėti ir išlaikyti įprotį", "Išlaidų sekimas: paprastas praktinis vadovas", "Praktinis išlaidų sekimo vadovas: pasirinkite kategorijas, peržiūrėkite banko operacijas ir paverskite duomenis aiškesniu mėnesio planu.", "Kaip sekti išlaidas neapsunkinant kasdienybės: duomenų surinkimas, kategorijos, mėnesio peržiūra ir dažniausios klaidos.", TRACKING),
        ("asmeninis-biudzetas", "Asmeninis biudžetas: kaip sudaryti veikiantį planą", "Asmeninis biudžetas: kaip sudaryti planą", "Sužinokite, kaip sudaryti asmeninį biudžetą: įrašyti pajamas, planuoti išlaidas, įtraukti tikslus ir palyginti planą su rezultatu.", "Žingsnis po žingsnio sudarykite asmeninį biudžetą, paremtą realiomis pajamomis, išlaidomis ir jūsų finansiniais tikslais.", BUDGET),
    ]
    for slug, title, meta_title, meta_description, excerpt, body in rows:
        Article.objects.update_or_create(slug=slug, defaults={"language":"lt", "title":title, "meta_title":meta_title, "meta_description":meta_description, "excerpt":excerpt, "body":body, "author_name":"MoneyCompass komanda", "status":"published", "published_at":now})


class Migration(migrations.Migration):
    dependencies = [("blog", "0002_seed_first_article")]
    operations = [migrations.RunPython(upsert, migrations.RunPython.noop)]
