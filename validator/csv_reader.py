import pandas as pd
from pandas.errors import EmptyDataError, ParserError

def read_csv(csv_path):
    try:
        df = pd.read_csv(csv_path)
        
        if df.empty:
            raise ValueError(f"CSV file at '{csv_path}' contains headers but no records.")
            
        return df

    except FileNotFoundError:
        raise FileNotFoundError(f"Error: The file at '{csv_path}' was not found.")

    except EmptyDataError:
        raise ValueError(f"Error: The file at '{csv_path}' is completely blank.")

    except (ParserError, UnicodeDecodeError) as e:
        raise ValueError(f"Error: The file at '{csv_path}' is corrupted or malformed. Details: {e}")