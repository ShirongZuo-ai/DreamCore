"""Architecture matching the official CBraMod implementation.

Adapted from wjq-learning/CBraMod at the revision recorded in provenance.py.
The upstream implementation and this isolated copy are MIT licensed.
"""

from __future__ import annotations

import copy


def build_cbramod(config):
    """Build CBraMod lazily so DreamCore does not require torch at startup."""

    import torch
    from torch import nn
    from torch.nn import functional as functional

    class CrissCrossLayer(nn.Module):
        def __init__(self):
            super().__init__()
            width = int(config["d_model"])
            heads = int(config["nhead"])
            dropout = float(config["dropout"])
            self.self_attn_s = nn.MultiheadAttention(
                width // 2, heads // 2, dropout=dropout, batch_first=True
            )
            self.self_attn_t = nn.MultiheadAttention(
                width // 2, heads // 2, dropout=dropout, batch_first=True
            )
            self.linear1 = nn.Linear(width, int(config["dim_feedforward"]))
            self.linear2 = nn.Linear(int(config["dim_feedforward"]), width)
            self.norm1 = nn.LayerNorm(width)
            self.norm2 = nn.LayerNorm(width)
            self.dropout = nn.Dropout(dropout)
            self.dropout1 = nn.Dropout(dropout)
            self.dropout2 = nn.Dropout(dropout)

        def forward(self, source):
            batch, channels, patches, width = source.shape
            normalized = self.norm1(source)
            spatial = (
                normalized[..., : width // 2]
                .transpose(1, 2)
                .reshape(batch * patches, channels, width // 2)
            )
            temporal = normalized[..., width // 2 :].reshape(batch * channels, patches, width // 2)
            spatial = self.self_attn_s(spatial, spatial, spatial, need_weights=False)[0]
            temporal = self.self_attn_t(temporal, temporal, temporal, need_weights=False)[0]
            spatial = spatial.reshape(batch, patches, channels, width // 2).transpose(1, 2)
            temporal = temporal.reshape(batch, channels, patches, width // 2)
            source = source + self.dropout1(torch.cat((spatial, temporal), dim=-1))
            normalized = self.norm2(source)
            feedforward = self.linear2(self.dropout(functional.gelu(self.linear1(normalized))))
            return source + self.dropout2(feedforward)

    class PatchEmbedding(nn.Module):
        def __init__(self):
            super().__init__()
            width = int(config["d_model"])
            patch_points = int(config["patch_points"])
            self.width = width
            self.mask_encoding = nn.Parameter(torch.zeros(patch_points), requires_grad=False)
            self.proj_in = nn.Sequential(
                nn.Conv2d(1, 25, kernel_size=(1, 49), stride=(1, 25), padding=(0, 24)),
                nn.GroupNorm(5, 25),
                nn.GELU(),
                nn.Conv2d(25, 25, kernel_size=(1, 3), padding=(0, 1)),
                nn.GroupNorm(5, 25),
                nn.GELU(),
                nn.Conv2d(25, 25, kernel_size=(1, 3), padding=(0, 1)),
                nn.GroupNorm(5, 25),
                nn.GELU(),
            )
            self.spectral_proj = nn.Sequential(
                nn.Linear(patch_points // 2 + 1, width), nn.Dropout(float(config["dropout"]))
            )
            self.positional_encoding = nn.Sequential(
                nn.Conv2d(width, width, kernel_size=(19, 7), padding=(9, 3), groups=width)
            )

        def forward(self, values):
            batch, channels, patches, points = values.shape
            flat = values.reshape(batch, 1, channels * patches, points)
            temporal = (
                self.proj_in(flat).permute(0, 2, 1, 3).reshape(batch, channels, patches, self.width)
            )
            spectrum = torch.abs(torch.fft.rfft(flat.reshape(-1, points), norm="forward"))
            spectral = self.spectral_proj(spectrum).reshape(batch, channels, patches, self.width)
            embedded = temporal + spectral
            position = self.positional_encoding(embedded.permute(0, 3, 1, 2)).permute(0, 2, 3, 1)
            return embedded + position

    class CBraMod(nn.Module):
        def __init__(self):
            super().__init__()
            self.patch_embedding = PatchEmbedding()
            layer = CrissCrossLayer()
            self.encoder = nn.Module()
            self.encoder.layers = nn.ModuleList(
                [copy.deepcopy(layer) for _ in range(int(config["layers"]))]
            )
            self.proj_out = nn.Sequential(nn.Linear(int(config["d_model"]), int(config["out_dim"])))

        def forward(self, values):
            output = self.patch_embedding(values)
            for layer in self.encoder.layers:
                output = layer(output)
            return self.proj_out(output)

    return CBraMod()
