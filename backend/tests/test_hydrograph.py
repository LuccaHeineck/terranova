import numpy as np
import pytest

from ingestion.hydrograph import (
    Hydrograph,
    discharge_to_inflow,
    find_boundary_inflow_mask,
    find_boundary_outlet,
    find_calibration_pairs,
    load_raw_stage_series,
    stage_to_discharge,
)

# Shape confirmed against a real download in Task 1 (see task-1-report.md) - root
# <DataTable xmlns="http://MRCS/"> wraps an inline xs:schema block (no readings,
# skip) and a <diffgr:diffgram><DocumentElement xmlns=""> holding the real rows.
# Note the row tag's real spelling (`DadosHidrometereologicos`, extra "re" - ANA's
# own inconsistency, not a typo) and the trailing space inside <DataHora> text.
_SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<DataTable xmlns="http://MRCS/">
  <xs:schema id="NewDataSet" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:msdata="urn:schemas-microsoft-com:xml-msdata" />
  <diffgr:diffgram xmlns:msdata="urn:schemas-microsoft-com:xml-msdata" xmlns:diffgr="urn:schemas-microsoft-com:xml-diffgram-v1">
    <DocumentElement xmlns="">
      <DadosHidrometereologicos diffgr:id="r1" msdata:rowOrder="0">
        <CodEstacao>86879300</CodEstacao>
        <DataHora>2024-05-01 00:30:00 </DataHora>
        <Vazao />
        <Nivel>1300.00</Nivel>
        <Chuva />
      </DadosHidrometereologicos>
      <DadosHidrometereologicos diffgr:id="r2" msdata:rowOrder="1">
        <CodEstacao>86879300</CodEstacao>
        <DataHora>2024-05-01 00:15:00 </DataHora>
        <Vazao>5000.00</Vazao>
        <Nivel>1250.00</Nivel>
        <Chuva />
      </DadosHidrometereologicos>
      <DadosHidrometereologicos diffgr:id="r3" msdata:rowOrder="2">
        <CodEstacao>86879300</CodEstacao>
        <DataHora>2024-05-01 00:00:00 </DataHora>
        <Vazao>10000.00</Vazao>
        <Nivel>1200.00</Nivel>
        <Chuva />
      </DadosHidrometereologicos>
    </DocumentElement>
  </diffgr:diffgram>
</DataTable>
"""


def test_stage_to_discharge_interpolates_linearly_between_breakpoints():
    curve = [(0.0, 0.0), (10.0, 100.0), (20.0, 500.0)]

    discharge = stage_to_discharge(np.array([5.0, 15.0]), rating_curve=curve)

    assert discharge.tolist() == pytest.approx([50.0, 300.0])


def test_stage_to_discharge_clips_to_nearest_endpoint_outside_curve_range():
    curve = [(0.0, 0.0), (10.0, 100.0)]

    discharge = stage_to_discharge(np.array([-5.0, 15.0]), rating_curve=curve)

    assert discharge.tolist() == pytest.approx([0.0, 100.0])


def test_load_raw_stage_series_parses_real_ana_response_shape(tmp_path):
    raw_path = tmp_path / "raw.xml"
    raw_path.write_text(_SAMPLE_XML)

    elapsed_seconds, stage_m = load_raw_stage_series(raw_path)

    # Rows arrive in descending time order in the real feed; the parser must
    # re-sort ascending before computing elapsed time.
    assert elapsed_seconds.tolist() == pytest.approx([0.0, 900.0, 1800.0])
    assert stage_m.tolist() == pytest.approx([12.0, 12.5, 13.0])  # cm -> m


def test_load_raw_stage_series_skips_rows_with_empty_nivel(tmp_path):
    raw_path = tmp_path / "raw.xml"
    # Empties r3's <Nivel> (the 00:00:00 / 12.0m reading), leaving r2 (00:15:00,
    # 12.5m) and r1 (00:30:00, 13.0m) as the two remaining rows, ascending.
    raw_path.write_text(_SAMPLE_XML.replace("<Nivel>1200.00</Nivel>", "<Nivel />"))

    elapsed_seconds, stage_m = load_raw_stage_series(raw_path)

    assert len(elapsed_seconds) == 2
    assert stage_m.tolist() == pytest.approx([12.5, 13.0])


def test_find_calibration_pairs_extracts_rows_with_both_nivel_and_vazao(tmp_path):
    raw_path = tmp_path / "raw.xml"
    raw_path.write_text(_SAMPLE_XML)

    pairs = find_calibration_pairs(raw_path)

    # Only the 2 rows with a non-empty <Vazao> contribute; sorted by stage.
    assert pairs == [(12.0, 10000.0), (12.5, 5000.0)]


def test_hydrograph_discharge_at_interpolates_between_samples():
    hydrograph = Hydrograph(
        elapsed_seconds=np.array([0.0, 900.0, 1800.0]),
        discharge_m3s=np.array([100.0, 200.0, 300.0]),
    )

    assert hydrograph.discharge_at(450.0) == pytest.approx(150.0)
    assert hydrograph.duration_seconds == pytest.approx(1800.0)


def test_hydrograph_discharge_at_raises_outside_recorded_range():
    hydrograph = Hydrograph(elapsed_seconds=np.array([0.0, 900.0]), discharge_m3s=np.array([100.0, 200.0]))

    with pytest.raises(ValueError, match="range"):
        hydrograph.discharge_at(1000.0)


def test_find_boundary_inflow_mask_locates_channel_on_given_edge():
    # A 5x5 synthetic terrain: the north edge has a clear low notch (the channel)
    # at columns 2-3, everywhere else is much higher.
    Z = np.full((5, 5), 100.0)
    Z[0, 2:4] = 10.0

    mask = find_boundary_inflow_mask(Z, edge="north")

    expected = np.zeros((5, 5), dtype=bool)
    expected[0, 2:4] = True
    assert np.array_equal(mask, expected)


def test_find_boundary_inflow_mask_rejects_invalid_edge():
    Z = np.full((5, 5), 100.0)

    with pytest.raises(ValueError, match="edge"):
        find_boundary_inflow_mask(Z, edge="northwest")


def test_find_boundary_outlet_marks_only_channel_cells_on_given_edge():
    # Same 5x5 synthetic terrain as the inflow-mask test, but checking the
    # south edge this time - only its channel notch (columns 1-2) should
    # become an outlet, not the rest of the south edge or any other edge.
    Z = np.full((5, 5), 100.0)
    Z[-1, 1:3] = 10.0
    N = np.full((5, 5), 0.05)

    boundary_elevation, boundary_roughness = find_boundary_outlet(Z, N, edge="south")

    assert boundary_elevation.shape == (7, 7)
    assert boundary_roughness.shape == (7, 7)
    # Outlet cells: lower than the real terrain by drop_m (default margin), not +inf.
    assert boundary_elevation[-1, 2] == pytest.approx(10.0 - 2.0)
    assert boundary_elevation[-1, 3] == pytest.approx(10.0 - 2.0)
    # Rest of the south edge, and every other edge, stays a wall.
    assert boundary_elevation[-1, 1] == np.inf
    assert boundary_elevation[-1, -2] == np.inf
    assert np.all(boundary_elevation[0, :] == np.inf)
    assert np.all(boundary_elevation[:, 0] == np.inf)
    assert np.all(boundary_elevation[:, -1] == np.inf)
    # Interior is untouched, matching Z/N exactly.
    np.testing.assert_array_equal(boundary_elevation[1:-1, 1:-1], Z)
    np.testing.assert_array_equal(boundary_roughness[1:-1, 1:-1], N)
    # Outlet roughness is water's Manning's n, not the wall's 1.0 placeholder.
    assert boundary_roughness[-1, 2] == pytest.approx(0.040)
    assert boundary_roughness[-1, 1] == pytest.approx(1.0)


def test_find_boundary_outlet_rejects_invalid_edge():
    Z = np.full((5, 5), 100.0)
    N = np.full((5, 5), 0.05)

    with pytest.raises(ValueError, match="edge"):
        find_boundary_outlet(Z, N, edge="northwest")


def test_discharge_to_inflow_splits_volume_uniformly_across_mask():
    mask = np.array([[True, False, True], [False, False, False], [False, False, False]])

    inflow = discharge_to_inflow(discharge_m3s=9.0, dt_seconds=100.0, mask=mask, cell_area_m2=900.0)

    # total volume = 9.0 m3/s * 100s = 900 m3; / 900 m2 cell area = 1.0 depth-unit
    # total, split evenly across the 2 masked cells.
    assert inflow[mask].tolist() == pytest.approx([0.5, 0.5])
    assert inflow[~mask].tolist() == pytest.approx([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])


def test_discharge_to_inflow_rejects_empty_mask():
    mask = np.zeros((3, 3), dtype=bool)

    with pytest.raises(ValueError, match="mask"):
        discharge_to_inflow(discharge_m3s=9.0, dt_seconds=100.0, mask=mask, cell_area_m2=900.0)
