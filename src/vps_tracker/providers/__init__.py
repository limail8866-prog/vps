from . import buyvm, cloudcone, dedirock, racknerd

PROVIDERS = {
    "racknerd": racknerd.fetch,
    "cloudcone": cloudcone.fetch,
    "dedirock": dedirock.fetch,
    "buyvm": buyvm.fetch,
}
