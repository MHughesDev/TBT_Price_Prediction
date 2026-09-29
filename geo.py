"""Clean up the raw Country / State fields.

lookup(country, state) -> (country_code, region_name). Unknown pairs give ('', '(Unknown)').
The key is the PAIR, because a state code alone is ambiguous (BC is British Columbia in
Canada but Baja California in Mexico), and the raw Country is itself wrong on a few rows.
"""

US_STATES = {
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

# How Mexican states are spelled in the raw data -> region name.
MEXICO_STATES = {
    'Nuevo Leon': ['NL', 'Leon'],
    'Baja California': ['BC', 'CA'],   # cities Mexicali, Tijuana, Tecate
    'Baja California Sur': ['BCS'],
    'Guanajuato': ['GTO'],
    'Coahuila': ['COAH', 'COUAHUILA'],
    'Queretaro': ['QRO'],
    'Tamaulipas': ['TAMPS'],
    'Jalisco': ['JAL', 'GUADALAJARA'],
    'Estado de Mexico': ['MEX', 'ESTADO DE MEXICO', 'ESTADO DE MÉXICO', 'EDO. DE MÉXICO',
                         'EDO. MEXICO', 'EDMX'],
    'Ciudad de Mexico': ['CDMX', 'CIUDAD DE MEXICO', 'MEXICO DF', 'NM'],  # NM = junk on Mexico City rows
    'Sinaloa': ['SIN'],
    'Veracruz': ['VER'],
    'San Luis Potosi': ['SLP'],
    'Sonora': ['SON'],
    'Chihuahua': ['CHIH'],
    'Hidalgo': ['HGO'],
    'Quintana Roo': ['QROO', 'QUINTANA RO'],
    'Yucatan': ['YUC'],
    'Aguascalientes': ['AGS'],
    'Tlaxcala': ['TLAX'],
    'Campeche': ['CAM'],
    'Michoacan': ['MICH'],
    'Tabasco': ['TAB', 'VILLAHERMOSA'],
    'Chiapas': ['CHIS'],
    'Puebla': ['PUE'],
    'Zacatecas': ['ZAC'],
    'Durango': ['DGO'],
    '(Unknown)': ['Mexico', 'El Salvador'],
}

# Everything else: (raw country, raw state) -> (country, region).
# Where the raw country is wrong, the city on those rows decided the answer.
OTHER = {
    ('US', 'Missouri'): ('US', 'Missouri'),
    ('US', 'Texas'): ('US', 'Texas'),
    ('MO', 'MA'): ('US', 'Massachusetts'),          # city Uxbridge; "MO" was a typo
    ('MX', 'VA'): ('US', 'Virginia'),               # city Blacksburg
    ('US', 'Ciudad de Mexico'): ('MX', 'Ciudad de Mexico'),
    ('US', 'Jalisco'): ('MX', 'Jalisco'),           # city Zapopan
    ('US', 'Ontario'): ('CA', 'Ontario'),           # city Timmins
    ('US', 'Guam'): ('GU', 'Guam'),
    ('GU', 'Guam'): ('GU', 'Guam'),
    ('PR', 'PR'): ('PR', 'Puerto Rico'),
    ('MX', 'Ciudad de Mexico'): ('MX', 'Ciudad de Mexico'),
    ('MX', 'Guadalajara'): ('MX', 'Jalisco'),
    ('MX', 'Villahermosa'): ('MX', 'Tabasco'),
    ('CA', 'QC'): ('CA', 'Quebec'), ('CA', 'AB'): ('CA', 'Alberta'),
    ('CA', 'ON'): ('CA', 'Ontario'), ('CA', 'SK'): ('CA', 'Saskatchewan'),
    ('CA', 'BC'): ('CA', 'British Columbia'), ('CA', 'NB'): ('CA', 'New Brunswick'),
    ('CA', 'MB'): ('CA', 'Manitoba'), ('CA', 'NS'): ('CA', 'Nova Scotia'),
    ('CA', 'Labrador'): ('CA', 'Newfoundland and Labrador'),
    ('CL', 'Chile'): ('CL', '(Unknown)'),
    ('CL', 'Region'): ('CL', 'Antofagasta'),
    ('CL', ''): ('CL', 'Antofagasta'),
    ('PE', 'Lima'): ('PE', 'Lima'), ('PE', 'Cusco'): ('PE', 'Cusco'),
    ('PE', 'Apurimac'): ('PE', 'Apurimac'), ('PE', 'Callao'): ('PE', 'Callao'),
    ('PE', 'Ancash'): ('PE', 'Ancash'), ('PE', 'La Libertad'): ('PE', 'La Libertad'),
    ('PE', 'Piura'): ('PE', 'Piura'), ('PE', 'Arequipa'): ('PE', 'Arequipa'),
    ('PE', 'Ica'): ('PE', 'Ica'), ('PE', 'Moquegua'): ('PE', 'Moquegua'),
    ('PE', 'Lambayeque'): ('PE', 'Lambayeque'), ('PE', 'Mariscal Nieto'): ('PE', 'Moquegua'),
    ('PE', 'Peru'): ('PE', 'Moquegua'),
    ('CO', 'Cundinamarca'): ('CO', 'Cundinamarca'), ('CO', 'Antioquia'): ('CO', 'Antioquia'),
    ('CO', 'Valle del Cauca'): ('CO', 'Valle del Cauca'), ('CO', 'Casanare'): ('CO', 'Casanare'),
    ('CO', 'Norte de Santander'): ('CO', 'Norte de Santander'),
    ('CO', 'Atlantico'): ('CO', 'Atlantico'), ('CO', 'Barranquilla'): ('CO', 'Atlantico'),
    ('CO', 'Boyacá'): ('CO', 'Boyaca'), ('CO', 'Meta'): ('CO', 'Meta'),
    ('CO', 'Santander'): ('CO', 'Santander'), ('CO', 'Caldas'): ('CO', 'Caldas'),
    ('CO', 'Bogotá'): ('CO', 'Bogota D.C.'), ('CO', 'Boliver'): ('CO', 'Bolivar'),
    ('CO', 'Colombia'): ('CO', '(Unknown)'),
    ('AR', 'Salta'): ('AR', 'Salta'), ('AR', 'Buenos Aires'): ('AR', 'Buenos Aires'),
    ('AR', 'Chaco'): ('AR', 'Chaco'), ('AR', 'Jujuy'): ('AR', 'Jujuy'),
    ('AR', 'Cordoba'): ('AR', 'Cordoba'), ('AR', 'San Juan'): ('AR', 'San Juan'),
    ('AR', 'Santa Fe'): ('AR', 'Santa Fe'), ('AR', 'Argentina'): ('AR', 'Salta'),
    ('AR', 'Los Andes'): ('AR', 'Salta'),
    ('EC', 'Guayas'): ('EC', 'Guayas'), ('EC', 'Santiago'): ('EC', 'Guayas'),  # city Guayaquil
    ('EC', 'Sector'): ('EC', 'Pichincha'),
    ('EC', 'Zamora Chinchipe'): ('EC', 'Zamora Chinchipe'),
    ('EC', 'Zamora-Chinchipe'): ('EC', 'Zamora Chinchipe'),
    ('PA', 'Panama'): ('PA', 'Panama'), ('PA', 'Panamá'): ('PA', 'Panama'),
    ('PA', 'Panama Province'): ('PA', 'Panama'), ('PA', 'Provincia de Colón'): ('PA', 'Colon'),
    ('PA', 'Colón'): ('PA', 'Colon'), ('PA', 'Changuinola'): ('PA', 'Bocas del Toro'),
    ('CR', 'Guanacaste'): ('CR', 'Guanacaste'), ('CR', 'Alajuela'): ('CR', 'Alajuela'),
    ('CR', 'San José'): ('CR', 'San Jose'), ('CR', 'Cartago'): ('CR', 'Cartago'),
    ('CR', 'Costa Rica'): ('CR', 'San Jose'),
    ('NI', 'León'): ('NI', 'Leon'), ('NI', 'Masaya'): ('NI', 'Masaya'),
    ('NI', 'Managua'): ('NI', 'Managua'),
    ('GT', 'San Marcos'): ('GT', 'San Marcos'), ('GT', 'Guatemala'): ('GT', 'Guatemala'),
    ('DO', 'Monte Cristi'): ('DO', 'Monte Cristi'), ('DO', 'Dominica'): ('DO', '(Unknown)'),
    ('DM', 'Roseau Valley'): ('DM', 'Saint George'),
    ('JM', 'Jamaica'): ('JM', 'Kingston'),
    ('LC', 'St. Lucia'): ('LC', 'Gros-Islet'),
    ('BS', 'Bahamas'): ('BS', 'New Providence'),
    ('BR', 'São Paulo'): ('BR', 'Sao Paulo'), ('BR', 'Sao Paulo'): ('BR', 'Sao Paulo'),
    ('UY', 'Montevideo'): ('UY', 'Montevideo'), ('UY', 'Soriano'): ('UY', 'Soriano'),
    ('GY', 'Guyana'): ('GY', 'Demerara-Mahaica'),
    ('SR', 'Paramaribo'): ('SR', 'Paramaribo'),
    ('ZA', 'Durban'): ('ZA', 'KwaZulu-Natal'),
    ('SA', 'Eastern Province'): ('SA', 'Eastern Province'),
    ('SA', 'TX'): ('SA', 'Eastern Province'),       # city Al Jubail; "TX" is junk
    ('PH', 'Batangas'): ('PH', 'Batangas'),
    ('TH', 'Bangkok'): ('TH', 'Bangkok'),
    ('LY', 'Tripoli'): ('LY', 'Tripoli'),
    ('EG', 'Egypt'): ('EG', 'Cairo'),
    ('IS', 'Keflavik'): ('IS', '(Unknown)'),
    ('ER', 'Bisha'): ('ER', 'Gash-Barka'),
    ('MH', 'Kwajalein'): ('MH', 'Kwajalein'),
    ('ML', ''): ('ML', 'Kidal'),
}

CHILE_REGIONS = {
    'Region Metropolitana de Santiago': ['SANTIAGO', 'SANTIAGO METROPOLITAN REGION', 'RM',
                                         'LAMPA', 'MELIPILLA'],
    'Antofagasta': ['ANTOFAGASTA', 'ANTOFAGSTA', 'ANTIFOGASTA REGION'],
    'Atacama': ['ATACAMA'],
    'Valparaiso': ['VALPARAÍSO', 'VALPARAISO', 'VALPARAISO REGIÓN', 'VAPARAISO'],
    'Biobio': ['BIO BIO'],
    "Libertador General Bernardo O'Higgins": ["O'HIGGINS", 'COLCHAGUA'],
    'La Araucania': ['LA ARAUCANIA'],
    'Magallanes y de la Antartica Chilena': ['MAGALLANES'],
    'Aysen del General Carlos Ibanez del Campo': ['REGIÓN DE AYSÉN'],
    'Tarapaca': ['TARAPACÁ'],
    'Maule': ['MALE'],
}


def _build_table():
    table = {('US', code): ('US', name) for code, name in US_STATES.items()}
    for region, spellings in MEXICO_STATES.items():
        table.update({('MX', s.upper()): ('MX', region) for s in spellings})
    for region, spellings in CHILE_REGIONS.items():
        table.update({('CL', s.upper()): ('CL', region) for s in spellings})
    table.update({(c.upper(), s.upper()): answer for (c, s), answer in OTHER.items()})
    return table


TABLE = _build_table()


def lookup(country, state):
    key = (str(country or '').strip().upper(), str(state or '').strip().upper())
    return TABLE.get(key, ('', '(Unknown)'))
