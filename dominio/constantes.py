"""Constantes y tablas base del simulador AgroVIA."""

ROSARIO_LAT = -32.9468
ROSARIO_LNG = -60.6393
BASE_PROD_MT = 80.0
COMBUSTIBLE_LKM = 0.35
FACTOR_CO2 = 2.68
TAX_RATE = 0.35
FEE_AGROVIA = 0.03
DLP_MIN_FACTOR = 0.80
HORIZON_YEARS = 5

# Base observada 2022 usada para la formula de interpolacion/escala.
EXPORTACION_BASE_CAPTURA_MT = 92.0
VIAJES_CAPTURADOS_BASE = 25_443.0

# Curva operativa proyectada (Año 1..Año 10): exportacion (Mt)
# y mercado total (viajes potenciales).
EXPORTACION_ESTIMADA_MT_SERIES = [
    101.0,
    98.7,
    97.7,
    98.4,
    99.4,
    99.9,
    100.8,
    101.7,
    102.8,
    104.2,
]

MERCADO_TOTAL_VIAJES_POTENCIALES_SERIES = [
    27868.76814734561,
    27207.195016251353,
    26931.539544962085,
    27124.498374864575,
    27400.15384615385,
    27538.0,
    27786.0,
    28034.0,
    28337.0,
    28723.0,
]

MATCHES_POTENCIALES_BY_YEAR = MERCADO_TOTAL_VIAJES_POTENCIALES_SERIES[:HORIZON_YEARS]

# Serie alternativa para modo "excel" (mismo horizonte de 5 años).
MATCHES_POTENCIALES_EXCEL = list(MATCHES_POTENCIALES_BY_YEAR)

INV_SOFTWARE = 162_763_200
INV_EQUIPOS_Y0_POR_PERSONA = 2_000_000
INV_SAS = 400_000
INV_MERIDIANO = 750_000
INV_FINVOI = 900_000
INV_APP_STORE_Y0 = 118_800
INV_GOOGLE_PLAY_Y0 = 30_000
INV_REGISTRO_MARCA_Y0 = 75_000
CAPITAL_TRABAJO = 45_056_103.38645834
PROMO_Y0 = 2_000_000
# Amortización lineal del intangible en 5 años (NIC 38).
AMORT_SOFTWARE_ANUAL = INV_SOFTWARE / 5
LAPTOP_AMORT_ANUAL = 140_000
COSTO_LEGAL_ADMIN = 2_500_000
PROMO_POR_ANO = {1: 3_500_000, 2: 2_000_000, 3: 2_000_000, 4: 1_000_000, 5: 1_000_000}

# AWS infrastructure costs by year (extracted from Excel Infra_AWS sheet)
AWS_POR_ANO = {
    1: dict(ec2=220_752, s3=27_703.06875, rds=216_000, maps=125_406, total=589_861.06875),
    2: dict(ec2=220_752, s3=67_504.2525, rds=216_000, maps=181_206, total=685_462.2525),
    3: dict(ec2=220_752, s3=120_497.805, rds=432_000, maps=242_388, total=1_015_637.805),
    4: dict(ec2=220_752, s3=192_816.10125, rds=432_000, maps=332_010, total=1_177_578.10125),
    5: dict(ec2=220_752, s3=278_621.74125, rds=878_400, maps=394_560, total=1_772_333.74125),
    6: dict(ec2=217_200, s3=658_800, rds=876_000, maps=686_400, total=2_438_400),
    7: dict(ec2=217_200, s3=824_400, rds=1_728_000, maps=694_800, total=3_464_400),
    8: dict(ec2=217_200, s3=991_200, rds=1_728_000, maps=703_200, total=3_639_600),
    9: dict(ec2=217_200, s3=1_159_200, rds=1_728_000, maps=711_600, total=3_816_000),
    10: dict(ec2=217_200, s3=1_330_800, rds=1_728_000, maps=720_000, total=3_996_000),
}

RETORNO_PRODUCTOS = {"Fertilizantes", "Harinas y derivados", "Arena para Construcción", "Arroz"}

# Exportacion estimada (Mt) usada por el horizonte operativo actual.
PROD_BY_YEAR = EXPORTACION_ESTIMADA_MT_SERIES[:HORIZON_YEARS]

# Curvas anuales indexadas como [base, año1..añoN].
ADOPTION_CURVE = [0.0, 0.25, 0.37, 0.50, 0.68, 0.80]
ADELANTO_PCT = [0.50, 0.50, 0.50, 0.50, 0.65, 0.65]
QP_TABLE = [0.32, 0.49, 0.53, 0.57, 0.61, 0.61]

RRHH_LOOKUP = [
    (0, 4, 162_763_200),
    (1, 7, 246_888_000),
    (8000, 8, 272_491_200),
    (12000, 9, 294_436_800),
    (17000, 10, 320_040_000),
]

AWS_LOOKUP = [
    (0, dict(ec2=0, s3=0, rds=0, maps=0, total=0)),
    (1, dict(ec2=220_752, s3=27_703.06875, rds=216_000, maps=125_406, total=589_861.06875)),
    (8000, dict(ec2=220_752, s3=67_504.2525, rds=216_000, maps=181_206, total=685_462.2525)),
    (12000, dict(ec2=220_752, s3=120_497.805, rds=432_000, maps=242_388, total=1_015_637.805)),
    (17000, dict(ec2=220_752, s3=192_816.10125, rds=432_000, maps=332_010, total=1_177_578.10125)),
    (21000, dict(ec2=220_752, s3=278_621.74125, rds=878_400, maps=394_560, total=1_772_333.74125)),
]