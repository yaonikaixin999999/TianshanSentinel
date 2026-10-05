import pytest

torch = pytest.importorskip("torch")

from tianshan_sentinel.model import TianshanSiameseNet


def test_model_preserves_spatial_shape():
    model = TianshanSiameseNet(pretrained=False, dropout=0.0).eval()
    tensor = torch.randn(1, 3, 64, 64)
    with torch.no_grad():
        output = model(tensor, tensor)
    assert tuple(output.shape) == (1, 1, 64, 64)

