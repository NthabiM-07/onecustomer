"""Reference lists shared by the synthetic generator and the matcher.

The matcher only uses ``NICKNAMES`` (a curated nickname table is standard in production record
linkage). Everything else here exists to make the synthetic population look like a South African
retail-credit book: common first names and surnames, street names, cities and postal codes.
"""

from __future__ import annotations

FEMALE_FIRST = [
    "Boitumelo", "Lerato", "Palesa", "Nomvula", "Thandeka", "Nokuthula", "Zanele", "Lindiwe",
    "Nompumelelo", "Refilwe", "Karabo", "Kgomotso", "Tshepiso", "Reabetswe", "Naledi", "Ayanda",
    "Precious", "Busisiwe", "Mpho", "Dineo", "Lesedi", "Masego", "Khanyisile", "Sibongile",
    "Noluthando", "Amahle", "Siphesihle", "Nandi", "Zodwa", "Rethabile", "Keabetswe", "Bontle",
    "Gugulethu", "Lebogang", "Mbali", "Anele", "Sarah", "Elizabeth", "Michelle", "Nicole",
    "Jessica", "Chantelle", "Marike", "Priya", "Kavitha", "Fatima", "Ayesha", "Natasha",
    "Charlene", "Maria", "Johanna", "Susan", "Angela", "Yolanda", "Nadia",
]

MALE_FIRST = [
    "Sibusiso", "Thabo", "Bongani", "Sipho", "Mandla", "Themba", "Lwazi", "Kagiso", "Tebogo",
    "Katlego", "Lebohang", "Tshepo", "Mthunzi", "Sizwe", "Neo", "Kabelo", "Lesego", "Vusumuzi",
    "Jabulani", "Andile", "Siyabonga", "Nkosinathi", "Bheki", "Musa", "Lucky", "Kgothatso",
    "Thulani", "Sello", "Teboho", "Karabo", "Mpho", "Ayanda", "Lebogang", "Johannes", "Pieter",
    "Jacobus", "Willem", "Hendrik", "Christopher", "Michael", "David", "Daniel", "Jason", "Ryan",
    "Ashwin", "Kevin", "Pravesh", "Mohammed", "Yusuf", "Francois", "Gerhard", "Ruan", "Tiaan",
    "Brandon",
]

# Formal name -> the short form people give when they sign up on an app.
NICKNAMES = {
    "BOITUMELO": "TUMI", "NOMPUMELELO": "MPUMI", "NOKUTHULA": "THULI", "GUGULETHU": "GUGU",
    "KGOMOTSO": "KGOMO", "TSHEPISO": "TSHEPI", "REABETSWE": "REA", "KHANYISILE": "KHANYI",
    "SIBONGILE": "BONGI", "NOLUTHANDO": "LULU", "SIPHESIHLE": "SPHE", "LEBOGANG": "LEBO",
    "LEBOHANG": "LEBO", "ELIZABETH": "LIZ", "MICHELLE": "SHELLY", "JOHANNA": "HANNA",
    "NATASHA": "TASHA", "SIBUSISO": "SBU", "BONGANI": "BONGI", "NKOSINATHI": "NATHI",
    "SIYABONGA": "SIYA", "VUSUMUZI": "VUSI", "JABULANI": "JABU", "KGOTHATSO": "KGOTSO",
    "JOHANNES": "JOHAN", "JACOBUS": "KOBUS", "HENDRIK": "HENK", "CHRISTOPHER": "CHRIS",
    "MICHAEL": "MIKE", "DANIEL": "DAN", "MOHAMMED": "MO", "KATLEGO": "KAT", "THEMBA": "TEMBI",
}

# Ordered roughly by frequency; the generator draws with Zipf-like weights.
SURNAMES = [
    "Dlamini", "Nkosi", "Ndlovu", "Khumalo", "Sithole", "Mahlangu", "Mokoena", "Mofokeng",
    "Molefe", "Mthembu", "Zulu", "Ngcobo", "Shabalala", "Tshabalala", "Radebe", "Maseko",
    "Mabaso", "Baloyi", "Maluleke", "Mathebula", "Hlongwane", "Mkhize", "Cele", "Zwane", "Moloi",
    "Letsoalo", "Phiri", "Modise", "Motaung", "Mokwena", "Masilela", "Makhubela", "Naidoo",
    "Pillay", "Govender", "Moodley", "Reddy", "Botha", "van der Merwe", "Pretorius",
    "du Plessis", "Fourie", "Steyn", "Kruger", "Venter", "Nel", "Coetzee", "Joubert", "van Wyk",
    "Smith", "Williams", "Jacobs", "Petersen", "Adams", "Abrahams", "Isaacs", "Hendricks",
]

STREETS = [
    "Main Road", "Church Street", "Voortrekker Road", "Jan Smuts Avenue", "Nelson Mandela Drive",
    "Oxford Road", "Beyers Naude Drive", "Pretorius Street", "Commissioner Street", "Rivonia Road",
    "Long Street", "Kerk Street", "Station Road", "Hospital Street", "Market Street", "Park Lane",
    "Protea Street", "Jacaranda Avenue", "Acacia Road", "Bloem Street", "Smit Street",
    "Vilakazi Street", "Albertina Sisulu Road", "Steve Biko Road", "Govan Mbeki Avenue",
]

# City -> (low, high) postal code range, inclusive.
CITIES = {
    "Johannesburg": (2000, 2199), "Soweto": (1800, 1868), "Pretoria": (1, 199),
    "Durban": (4001, 4099), "Cape Town": (7700, 8001), "Gqeberha": (6001, 6070),
    "Bloemfontein": (9300, 9330), "Polokwane": (700, 727), "Mbombela": (1200, 1218),
    "Rustenburg": (299, 309), "Potchefstroom": (2520, 2531), "Kimberley": (8300, 8345),
    "East London": (5200, 5247), "Pietermaritzburg": (3200, 3299), "Klerksdorp": (2570, 2575),
}

EMAIL_DOMAINS = ["gmail.com", "outlook.com", "yahoo.com", "icloud.com", "webmail.co.za", "mweb.co.za"]

MOBILE_PREFIXES = ["060", "061", "062", "063", "064", "065", "066", "067", "068", "071", "072",
                   "073", "074", "076", "078", "079", "081", "082", "083", "084"]

STREET_ABBREVIATIONS = {"Street": "St", "Road": "Rd", "Avenue": "Ave", "Drive": "Dr", "Lane": "Ln"}
