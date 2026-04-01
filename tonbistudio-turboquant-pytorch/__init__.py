try:
    from .turboquant import TurboQuantMSE, TurboQuantProd, TurboQuantKVCache
    from .lloyd_max import LloydMaxCodebook, solve_lloyd_max
    from .compressors import TurboQuantCompressorV2, TurboQuantCompressorMSE
except Exception:
    # Allow importing the package modules when running tests directly
    from turboquant import TurboQuantMSE, TurboQuantProd, TurboQuantKVCache
    from lloyd_max import LloydMaxCodebook, solve_lloyd_max
    from compressors import TurboQuantCompressorV2, TurboQuantCompressorMSE
