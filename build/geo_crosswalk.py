"""P0-2: geographic crosswalk for the raw Country / State fields.

WHY THE KEY IS Country|State, NOT State ALONE
---------------------------------------------
HANDOFF.md P0-2 asks for a crosswalk "raw -> ISO region + country" keyed on `State`.
A State-only key cannot be correct on this data, because ten State values span more
than one country and resolve differently in each:

    BC + CA -> British Columbia      BC + MX -> Baja California
    CA + US -> California            CA + MX -> Baja California (city: Tecate)
    Santiago + CL -> Metropolitana   Santiago + EC -> Guayas (city: Guayaquil)

So the key is the composite `UPPER(TRIM(Country)) & "|" & UPPER(TRIM(State))`.
That is 219 distinct pairs across the 7,480 source rows - small enough to curate by hand
and verify against the City column. This is an extension of the P0-2 spec, not a reversal
of a locked decision in HANDOFF.md section 6 (which says nothing about geography).

THE COUNTRY COLUMN IS ALSO DIRTY
--------------------------------
`Country` is not trustworthy on its own either. Confirmed data-entry errors, each
adjudicated against the City column:

    MO|MA   -> Uxbridge is in Massachusetts, US.     Country was a typo for US.
    MX|VA   -> Blacksburg is in Virginia, US.        Country wrong.
    US|Jalisco -> Zapopan is in Jalisco, Mexico.     Country wrong.
    US|Ontario -> Timmins is in Ontario, Canada.     Country wrong.
    US|Ciudad de Mexico -> Cuauhtemoc, Mexico.       Country wrong.
    SA|TX   -> Al Jubail is in Saudi Arabia.         State was junk, country right.
    MX|NM   -> Mexico City.                          State was junk, country right.

So the crosswalk emits a corrected `Country Normalized` as well as `State Normalized`.

MATCH LEVEL
-----------
Not every row can be resolved to a region, and inventing one would be worse than
admitting it. Each entry carries a level:

    region   - resolved to a specific first-level subdivision, ISO 3166-2 code given
    country  - country is certain, region is not (value was a city, a country name,
               or a region that does not map cleanly). Region Code left blank.
    none     - not a real location (test/demo rows, blank)
"""

# ---------------------------------------------------------------- US states
_US = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California',
    'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware', 'FL': 'Florida', 'GA': 'Georgia',
    'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa',
    'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
    'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire',
    'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York', 'NC': 'North Carolina',
    'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania',
    'RI': 'Rhode Island', 'SC': 'South Carolina', 'SD': 'South Dakota', 'TN': 'Tennessee',
    'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington',
    'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming', 'DC': 'District of Columbia',
}

_MX = {  # ISO 3166-2:MX suffix -> canonical name
    'AGU': 'Aguascalientes', 'BCN': 'Baja California', 'BCS': 'Baja California Sur',
    'CAM': 'Campeche', 'CHP': 'Chiapas', 'CHH': 'Chihuahua', 'CMX': 'Ciudad de Mexico',
    'COA': 'Coahuila', 'COL': 'Colima', 'DUR': 'Durango', 'GUA': 'Guanajuato',
    'GRO': 'Guerrero', 'HID': 'Hidalgo', 'JAL': 'Jalisco', 'MEX': 'Estado de Mexico',
    'MIC': 'Michoacan', 'MOR': 'Morelos', 'NAY': 'Nayarit', 'NLE': 'Nuevo Leon',
    'OAX': 'Oaxaca', 'PUE': 'Puebla', 'QUE': 'Queretaro', 'ROO': 'Quintana Roo',
    'SLP': 'San Luis Potosi', 'SIN': 'Sinaloa', 'SON': 'Sonora', 'TAB': 'Tabasco',
    'TAM': 'Tamaulipas', 'TLA': 'Tlaxcala', 'VER': 'Veracruz', 'YUC': 'Yucatan',
    'ZAC': 'Zacatecas',
}

COUNTRY_NAMES = {
    'US': 'United States', 'MX': 'Mexico', 'CA': 'Canada', 'PE': 'Peru', 'AR': 'Argentina',
    'CL': 'Chile', 'CO': 'Colombia', 'EC': 'Ecuador', 'PA': 'Panama', 'NI': 'Nicaragua',
    'GU': 'Guam', 'CR': 'Costa Rica', 'UY': 'Uruguay', 'ZA': 'South Africa', 'BR': 'Brazil',
    'PR': 'Puerto Rico', 'GT': 'Guatemala', 'GY': 'Guyana', 'SR': 'Suriname', 'JM': 'Jamaica',
    'SA': 'Saudi Arabia', 'LY': 'Libya', 'PH': 'Philippines', 'DO': 'Dominican Republic',
    'TH': 'Thailand', 'LC': 'Saint Lucia', 'EG': 'Egypt', 'IS': 'Iceland', 'ER': 'Eritrea',
    'DM': 'Dominica', 'ML': 'Mali', 'MH': 'Marshall Islands', 'BS': 'Bahamas',
    'SV': 'El Salvador', '': '(Unknown)',
}

# (raw_country, raw_state) -> (country_iso, region_name, region_code, level, note)
# 'note' is only filled where the source data was wrong or ambiguous.
_X = {}

def _add(cc, st, country, region, code, level='region', note=''):
    _X[(cc.upper(), st.upper())] = (country, region, code, level, note)

# ---- United States -------------------------------------------------------
for ab, nm in _US.items():
    _add('US', ab, 'US', nm, f'US-{ab}')
_add('US', 'Missouri', 'US', 'Missouri', 'US-MO')
_add('US', 'Texas', 'US', 'Texas', 'US-TX')
_add('US', 'Guam', 'GU', 'Guam', 'GU-GU', 'region',
     'Asan is in Guam, a US territory; Country normalized to GU for consistency with the 23 GU rows.')
_add('GU', 'Guam', 'GU', 'Guam', 'GU-GU')
_add('PR', 'PR', 'PR', 'Puerto Rico', 'PR-PR')
# US rows whose Country is wrong
_add('MO', 'MA', 'US', 'Massachusetts', 'US-MA', 'region',
     'City Uxbridge is in Massachusetts. Country "MO" is a data-entry error (Macao), not Missouri.')
_add('MX', 'VA', 'US', 'Virginia', 'US-VA', 'region',
     'City Blacksburg is in Virginia, US. Country "MX" is a data-entry error.')
_add('US', 'Sample', '', '(Not a location)', '', 'none',
     'Test row: State "Sample", City "Fm >500". Excluded by DQ Looks Non-Tank.')

# ---- Mexico --------------------------------------------------------------
_MX_ALIAS = {
    'NL': 'NLE', 'BC': 'BCN', 'CA': 'BCN', 'GTO': 'GUA', 'COAH': 'COA', 'COUAHUILA': 'COA',
    'QRO': 'QUE', 'TAMPS': 'TAM', 'JAL': 'JAL', 'MEX': 'MEX', 'SIN': 'SIN', 'VER': 'VER',
    'SLP': 'SLP', 'SON': 'SON', 'CHIH': 'CHH', 'HGO': 'HID', 'QROO': 'ROO',
    'QUINTANA RO': 'ROO', 'YUC': 'YUC', 'AGS': 'AGU', 'TLAX': 'TLA', 'CDMX': 'CMX',
    'CAM': 'CAM', 'MICH': 'MIC', 'TAB': 'TAB', 'BCS': 'BCS', 'CHIS': 'CHP', 'PUE': 'PUE',
    'ZAC': 'ZAC', 'DGO': 'DUR',
    'ESTADO DE MEXICO': 'MEX', 'ESTADO DE MÉXICO': 'MEX', 'EDO. DE MÉXICO': 'MEX',
    'EDO. MEXICO': 'MEX', 'EDMX': 'MEX', 'CIUDAD DE MEXICO': 'CMX', 'MEXICO DF': 'CMX',
    'GUADALAJARA': 'JAL', 'VILLAHERMOSA': 'TAB',
}
for raw, iso in _MX_ALIAS.items():
    _add('MX', raw, 'MX', _MX[iso], f'MX-{iso}')
_add('MX', 'BC', 'MX', 'Baja California', 'MX-BCN', 'region',
     'Cities Mexicali/Tijuana. Distinct from CA|BC = British Columbia, Canada.')
_add('MX', 'CA', 'MX', 'Baja California', 'MX-BCN', 'region',
     'City Tecate. "CA" here is Baja California, not California.')
_add('MX', 'Leon', 'MX', 'Nuevo Leon', 'MX-NLE', 'region',
     'City General Escobedo is in Nuevo Leon. "Leon" is the city of Leon, Guanajuato elsewhere - City disambiguates.')
_add('MX', 'Guadalajara', 'MX', 'Jalisco', 'MX-JAL', 'region', 'City name used in the State field.')
_add('MX', 'Villahermosa', 'MX', 'Tabasco', 'MX-TAB', 'region', 'City name used in the State field.')
_add('MX', 'Mexico', 'MX', '(Unknown)', '', 'country',
     'Country name in the State field; cities Hidalgo/Zacatecas span two states, so no region assigned.')
_add('MX', 'NM', 'MX', 'Ciudad de Mexico', 'MX-CMX', 'region',
     'City Mexico City. State "NM" is junk (New Mexico abbreviation entered on Mexican rows).')
_add('MX', 'Ciudad de Mexico', 'MX', 'Ciudad de Mexico', 'MX-CMX')
_add('US', 'Ciudad de Mexico', 'MX', 'Ciudad de Mexico', 'MX-CMX', 'region',
     'City Cuauhtemoc. Country "US" is a data-entry error.')
_add('US', 'Jalisco', 'MX', 'Jalisco', 'MX-JAL', 'region',
     'City Zapopan is in Jalisco, Mexico. Country "US" is a data-entry error.')
_add('MX', 'El Salvador', 'MX', '(Unknown)', '', 'country',
     'AMBIGUOUS: City "San Salvador". There is a San Salvador in Hidalgo, Mexico and a capital of El Salvador. '
     'Country kept as MX per the source; confirm with the estimating team.')

# ---- Canada --------------------------------------------------------------
for ab, nm in {'QC': 'Quebec', 'AB': 'Alberta', 'ON': 'Ontario', 'SK': 'Saskatchewan',
               'BC': 'British Columbia', 'NB': 'New Brunswick', 'MB': 'Manitoba',
               'NS': 'Nova Scotia'}.items():
    _add('CA', ab, 'CA', nm, f'CA-{ab}')
_add('CA', 'Labrador', 'CA', 'Newfoundland and Labrador', 'CA-NL', 'region', 'City "Newfoundland".')
_add('US', 'Ontario', 'CA', 'Ontario', 'CA-ON', 'region',
     'City Timmins is in Ontario, Canada. Country "US" is a data-entry error.')

# ---- Chile ---------------------------------------------------------------
_CL = {
    'SANTIAGO': ('Region Metropolitana de Santiago', 'CL-RM'),
    'SANTIAGO METROPOLITAN REGION': ('Region Metropolitana de Santiago', 'CL-RM'),
    'RM': ('Region Metropolitana de Santiago', 'CL-RM'),
    'LAMPA': ('Region Metropolitana de Santiago', 'CL-RM'),
    'MELIPILLA': ('Region Metropolitana de Santiago', 'CL-RM'),
    'ANTOFAGASTA': ('Antofagasta', 'CL-AN'), 'ANTOFAGSTA': ('Antofagasta', 'CL-AN'),
    'ANTIFOGASTA REGION': ('Antofagasta', 'CL-AN'),
    'ATACAMA': ('Atacama', 'CL-AT'),
    'VALPARAÍSO': ('Valparaiso', 'CL-VS'), 'VALPARAISO': ('Valparaiso', 'CL-VS'),
    'VALPARAISO REGIÓN': ('Valparaiso', 'CL-VS'), 'VAPARAISO': ('Valparaiso', 'CL-VS'),
    'BIO BIO': ('Biobio', 'CL-BI'),
    "O'HIGGINS": ("Libertador General Bernardo O'Higgins", 'CL-LI'),
    'COLCHAGUA': ("Libertador General Bernardo O'Higgins", 'CL-LI'),
    'LA ARAUCANIA': ('La Araucania', 'CL-AR'),
    'MAGALLANES': ('Magallanes y de la Antartica Chilena', 'CL-MA'),
    'REGIÓN DE AYSÉN': ('Aysen del General Carlos Ibanez del Campo', 'CL-AI'),
    'TARAPACÁ': ('Tarapaca', 'CL-TA'),
    'MALE': ('Maule', 'CL-ML'),
}
for raw, (nm, code) in _CL.items():
    _add('CL', raw, 'CL', nm, code)
_X[('CL', 'MALE')] = ('CL', 'Maule', 'CL-ML', 'region',
                      'City Talca is in Maule. "Male" is a misspelling.')
_X[('CL', 'ANTOFAGSTA')] = ('CL', 'Antofagasta', 'CL-AN', 'region', 'Misspelling of Antofagasta.')
_X[('CL', 'VAPARAISO')] = ('CL', 'Valparaiso', 'CL-VS', 'region', 'Misspelling of Valparaiso.')
_add('CL', 'Region', 'CL', 'Antofagasta', 'CL-AN', 'region',
     'State field held the literal word "Region"; City "Antofagasta" supplies the region.')
_add('CL', 'Chile', 'CL', '(Unknown)', '', 'country',
     'Country name in the State field. City Panguipulli is in Los Rios, but a single row - left at country level.')
_add('CL', '', 'CL', 'Antofagasta', 'CL-AN', 'region', 'Blank State; City "El Loa" is a province of Antofagasta.')

# ---- Peru ----------------------------------------------------------------
for raw, nm, code in [
    ('Lima', 'Lima', 'PE-LIM'), ('Cusco', 'Cusco', 'PE-CUS'), ('Apurimac', 'Apurimac', 'PE-APU'),
    ('Callao', 'Callao', 'PE-CAL'), ('Ancash', 'Ancash', 'PE-ANC'),
    ('La Libertad', 'La Libertad', 'PE-LAL'), ('Piura', 'Piura', 'PE-PIU'),
    ('Arequipa', 'Arequipa', 'PE-ARE'), ('ICA', 'Ica', 'PE-ICA'), ('Ica', 'Ica', 'PE-ICA'),
    ('Moquegua', 'Moquegua', 'PE-MOQ'), ('Lambayeque', 'Lambayeque', 'PE-LAM')]:
    _add('PE', raw, 'PE', nm, code)
_add('PE', 'Mariscal Nieto', 'PE', 'Moquegua', 'PE-MOQ', 'region',
     'Mariscal Nieto is a province of Moquegua.')
_add('PE', 'Peru', 'PE', 'Moquegua', 'PE-MOQ', 'region',
     'Country name in the State field; City "Quellaveco" is a mine in Moquegua.')

# ---- Colombia ------------------------------------------------------------
for raw, nm, code in [
    ('Cundinamarca', 'Cundinamarca', 'CO-CUN'), ('Antioquia', 'Antioquia', 'CO-ANT'),
    ('Valle del Cauca', 'Valle del Cauca', 'CO-VAC'), ('Casanare', 'Casanare', 'CO-CAS'),
    ('Norte de Santander', 'Norte de Santander', 'CO-NSA'), ('Atlantico', 'Atlantico', 'CO-ATL'),
    ('Boyacá', 'Boyaca', 'CO-BOY'), ('Meta', 'Meta', 'CO-MET'),
    ('Santander', 'Santander', 'CO-SAN'), ('Caldas', 'Caldas', 'CO-CAL')]:
    _add('CO', raw, 'CO', nm, code)
_add('CO', 'Barranquilla', 'CO', 'Atlantico', 'CO-ATL', 'region',
     'Barranquilla is the capital of Atlantico; City Malambo is in Atlantico.')
_add('CO', 'Bogotá', 'CO', 'Bogota D.C.', 'CO-DC')
_add('CO', 'Boliver', 'CO', 'Bolivar', 'CO-BOL', 'region',
     'Misspelling of Bolivar; City Cartagena is its capital.')
_add('CO', 'Colombia', 'CO', '(Unknown)', '', 'country', 'Country name in both the State and City fields.')

# ---- Argentina -----------------------------------------------------------
for raw, nm, code in [
    ('Salta', 'Salta', 'AR-A'), ('Buenos Aires', 'Buenos Aires', 'AR-B'),
    ('Chaco', 'Chaco', 'AR-H'), ('Jujuy', 'Jujuy', 'AR-Y'), ('Cordoba', 'Cordoba', 'AR-X'),
    ('San Juan', 'San Juan', 'AR-J'), ('Santa Fe', 'Santa Fe', 'AR-S')]:
    _add('AR', raw, 'AR', nm, code)
_add('AR', 'Argentina', 'AR', 'Salta', 'AR-A', 'region',
     'Country name in the State field; every City on these 62 rows is Salta.')
_add('AR', 'Los Andes', 'AR', 'Salta', 'AR-A', 'region',
     'Los Andes is a department of Salta; City "Santa Rosa de los Pastos Grandes" is in it.')

# ---- Ecuador -------------------------------------------------------------
_add('EC', 'Guayas', 'EC', 'Guayas', 'EC-G')
_add('EC', 'Santiago', 'EC', 'Guayas', 'EC-G', 'region',
     'City Guayaquil is in Guayas. Distinct from CL|Santiago = Region Metropolitana.')
_add('EC', 'Sector', 'EC', 'Pichincha', 'EC-P', 'region',
     'State field held the literal word "Sector"; City Quito is in Pichincha.')
_add('EC', 'Zamora Chinchipe', 'EC', 'Zamora Chinchipe', 'EC-Z')
_add('EC', 'Zamora-Chinchipe', 'EC', 'Zamora Chinchipe', 'EC-Z')

# ---- Central America / Caribbean ----------------------------------------
_add('PA', 'Panama', 'PA', 'Panama', 'PA-8')
_add('PA', 'Panamá', 'PA', 'Panama', 'PA-8')
_add('PA', 'Panama Province', 'PA', 'Panama', 'PA-8')
_add('PA', 'Provincia de Colón', 'PA', 'Colon', 'PA-3')
_add('PA', 'Colón', 'PA', 'Colon', 'PA-3')
_add('PA', 'Changuinola', 'PA', 'Bocas del Toro', 'PA-1', 'region',
     'Changuinola is a district of Bocas del Toro.')
_add('CR', 'Guanacaste', 'CR', 'Guanacaste', 'CR-G')
_add('CR', 'Alajuela', 'CR', 'Alajuela', 'CR-A')
_add('CR', 'San José', 'CR', 'San Jose', 'CR-SJ')
_add('CR', 'Cartago', 'CR', 'Cartago', 'CR-C')
_add('CR', 'Costa Rica', 'CR', 'San Jose', 'CR-SJ', 'region',
     "Country name in the State field; City \"San Jose'\".")
_add('NI', 'León', 'NI', 'Leon', 'NI-LE')
_add('NI', 'Masaya', 'NI', 'Masaya', 'NI-MS')
_add('NI', 'Managua', 'NI', 'Managua', 'NI-MN')
_add('GT', 'San Marcos', 'GT', 'San Marcos', 'GT-SM')
_add('GT', 'Guatemala', 'GT', 'Guatemala', 'GT-GU')
_add('DO', 'Monte Cristi', 'DO', 'Monte Cristi', 'DO-15')
_add('DO', 'Dominica', 'DO', '(Unknown)', '', 'country',
     'State "Dominica" with Country DO (Dominican Republic); City "Punta Bergantin" not confidently placed.')
_add('DM', 'Roseau Valley', 'DM', 'Saint George', 'DM-04', 'region', 'Roseau Valley is in Saint George parish.')
_add('JM', 'Jamaica', 'JM', 'Kingston', 'JM-01', 'region', 'City Kingston.')
_add('LC', 'St. Lucia', 'LC', 'Gros-Islet', 'LC-05', 'region', 'City Gros Islet.')
_add('BS', 'Bahamas', 'BS', 'New Providence', 'BS-NP', 'region', 'City Nassau.')
_add('PR', 'PR', 'PR', 'Puerto Rico', 'PR-PR')

# ---- South America (other) ----------------------------------------------
_add('BR', 'São Paulo', 'BR', 'Sao Paulo', 'BR-SP')
_add('BR', 'Sao Paulo', 'BR', 'Sao Paulo', 'BR-SP')
_add('UY', 'Montevideo', 'UY', 'Montevideo', 'UY-MO')
_add('UY', 'Soriano', 'UY', 'Soriano', 'UY-SO')
_add('GY', 'Guyana', 'GY', 'Demerara-Mahaica', 'GY-DE', 'region', 'City Georgetown.')
_add('SR', 'Paramaribo', 'SR', 'Paramaribo', 'SR-PM')

# ---- Rest of world -------------------------------------------------------
_add('ZA', 'Durban', 'ZA', 'KwaZulu-Natal', 'ZA-KZN', 'region', 'Durban is in KwaZulu-Natal.')
_add('SA', 'Eastern Province', 'SA', 'Eastern Province', 'SA-04')
_add('SA', 'TX', 'SA', 'Eastern Province', 'SA-04', 'region',
     'City "Al Jubail" is in the Eastern Province of Saudi Arabia. State "TX" is junk.')
_add('PH', 'Batangas', 'PH', 'Batangas', 'PH-BTG')
_add('TH', 'Bangkok', 'TH', 'Bangkok', 'TH-10')
_add('LY', 'Tripoli', 'LY', 'Tripoli', 'LY-TB')
_add('EG', 'Egypt', 'EG', 'Cairo', 'EG-C', 'region', 'City Cairo.')
_add('IS', 'Keflavik', 'IS', '(Unknown)', '', 'country',
     'Keflavik is a town, not an Icelandic first-level region.')
_add('ER', 'Bisha', 'ER', 'Gash-Barka', 'ER-GB', 'region', 'Bisha mine is in Gash-Barka.')
_add('MH', 'Kwajalein', 'MH', 'Kwajalein', 'MH-KWA')
_add('ML', '', 'ML', 'Kidal', 'ML-8', 'region', 'Blank State; City Kidal.')

# ---- Not a location ------------------------------------------------------
_add('', '', '', '(Unknown)', '', 'none',
     'Both Country and State blank. 22 rows, all test/demo quotes excluded by DQ Looks Non-Tank.')


def lookup(country, state):
    """Return (country_iso, country_name, region_name, region_code, level, note)."""
    k = (str(country or '').strip().upper(), str(state or '').strip().upper())
    if k in _X:
        cc, rg, code, lvl, note = _X[k]
        return cc, COUNTRY_NAMES.get(cc, cc or '(Unknown)'), rg, code, lvl, note
    return '', '(Unknown)', '(Unknown)', '', 'none', 'No crosswalk entry'


def rows():
    """Crosswalk as a sorted list of rows for writing to Ref_Lists."""
    out = []
    for (cc_raw, st_raw), (cc, rg, code, lvl, note) in _X.items():
        out.append([f'{cc_raw}|{st_raw}', cc_raw, st_raw, cc,
                    COUNTRY_NAMES.get(cc, cc or '(Unknown)'), rg, code, lvl, note])
    return sorted(out, key=lambda r: (r[3], r[5], r[0]))


HEADERS = ['Geo Key', 'Country Raw', 'State Raw', 'Country Normalized', 'Country Name',
           'State Normalized', 'Region Code', 'Geo Match Level', 'Note']

if __name__ == '__main__':
    for r in rows():
        print(' | '.join(str(x)[:26] for x in r[:8]))
    print(f'\n{len(_X)} crosswalk entries')
