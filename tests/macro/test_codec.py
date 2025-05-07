from pathlib import Path

def test_codec():
    source = Path(__file__).parent / "codec"
    
    def process(path: Path):
        return path.read_text(encoding="magic.macro")
    
    for file in source.rglob("*"):
        if not file.is_file():
            continue

        if file.name.startswith('_'):
            continue
        print(f"running {file}")
        process(file)

if __name__ == "__main__":
    test_codec()