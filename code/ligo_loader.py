import pandas as pd
from gwpy.timeseries import TimeSeries


def load_ligo_data():
    print("Downloading LIGO strain data (GW150914)...")

    strain = TimeSeries.fetch_open_data(
        "H1",
        1126259446,
        1126259478,
        sample_rate=4096
    )

    df = pd.DataFrame({
        "time": strain.times.value,
        "strain": strain.value
    })

    return df
