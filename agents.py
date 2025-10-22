from extract_data import llama_parse_md
from create_database import create_data

import config

data = config.PARSE_DATA_DIR

llama_parse_md(data)

create_data()
