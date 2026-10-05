import ifcopenshell.api as api
import pytest


@pytest.fixture
def wall_ifc(tmp_path):
    """A minimal IFC4 model with a single 5 x 0.2 x 3 m wall."""
    model = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name="Test")
    api.run("unit.assign_unit", model)
    context = api.run("context.add_context", model, context_type="Model")
    body = api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context,
    )
    site = api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    wall = api.run("root.create_entity", model, ifc_class="IfcWall", name="Wall")
    api.run("spatial.assign_container", model, relating_structure=site, products=[wall])
    representation = api.run(
        "geometry.add_wall_representation", model, context=body, length=5, height=3, thickness=0.2
    )
    api.run("geometry.assign_representation", model, product=wall, representation=representation)
    api.run("geometry.edit_object_placement", model, product=wall)

    path = tmp_path / "wall.ifc"
    model.write(str(path))
    return path


@pytest.fixture
def storey_ifc(tmp_path):
    """An IFC4 model with a storey "EG" holding a red wall (with a pset) and a slab."""
    model = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", model, ifc_class="IfcProject", name="Test")
    api.run("unit.assign_unit", model)
    context = api.run("context.add_context", model, context_type="Model")
    body = api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context,
    )
    site = api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Building")
    storey = api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="EG")
    api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    api.run("aggregate.assign_object", model, relating_object=building, products=[storey])

    wall = api.run("root.create_entity", model, ifc_class="IfcWall", name="Wall")
    wall_rep = api.run(
        "geometry.add_wall_representation", model, context=body, length=5, height=3, thickness=0.2
    )
    api.run("geometry.assign_representation", model, product=wall, representation=wall_rep)
    api.run("geometry.edit_object_placement", model, product=wall)
    style = api.run("style.add_style", model, name="Red")
    api.run(
        "style.add_surface_style", model, style=style, ifc_class="IfcSurfaceStyleShading",
        attributes={"SurfaceColour": {"Name": None, "Red": 1.0, "Green": 0.0, "Blue": 0.0}, "Transparency": 0.0},
    )
    api.run("style.assign_representation_styles", model, shape_representation=wall_rep, styles=[style])
    pset = api.run("pset.add_pset", model, product=wall, name="Pset_WallCommon")
    api.run("pset.edit_pset", model, pset=pset, properties={"IsExternal": True, "Reference": "AW-01"})

    slab = api.run("root.create_entity", model, ifc_class="IfcSlab", name=None)
    slab_rep = api.run(
        "geometry.add_wall_representation", model, context=body, length=4, height=0.3, thickness=4
    )
    api.run("geometry.assign_representation", model, product=slab, representation=slab_rep)
    api.run("geometry.edit_object_placement", model, product=slab)
    api.run("spatial.assign_container", model, relating_structure=storey, products=[wall, slab])

    path = tmp_path / "storey.ifc"
    model.write(str(path))
    return path
