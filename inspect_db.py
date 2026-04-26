import lancedb

db_path = "/Users/gilsonsiqueira/mcpServers/mcp-plesk-unified/storage/lancedb_medium"
db = lancedb.connect(db_path)
print(f"Tables: {db.table_names()}")

table = db.open_table("plesk_knowledge")
print(f"Count: {table.count_rows()}")
print("Schema:")
print(table.schema)

# Sample one row
print("\nSample row:")
print(table.to_pandas().head(1).to_dict("records")[0])
