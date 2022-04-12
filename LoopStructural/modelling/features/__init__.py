from enum import IntEnum
from LoopStructural.utils import getLogger


class FeatureType(IntEnum):
    """
    Enum for the different interpolator types

    1-9 should cover interpolators with supports
    9+ are data supported
    """

    BASE = 0
    INTERPOLATED = 1
    STRUCTURALFRAME = 2
    REGION = 3
    FOLDEDFEATURE = 4
    ANALYTICALFEATURE = 5
    LAMBDAFEATURE = 6


from ._base_geological_feature import BaseFeature
from ._geological_feature import GeologicalFeature
from ._lambda_geological_feature import LambdaGeologicalFeature
from .geological_feature_builder import GeologicalFeatureBuilder
from .region_feature import RegionFeature
from ._structural_frame import StructuralFrame
from .builders._structural_frame_builder import StructuralFrameBuilder
from ._unconformity_feature import UnconformityFeature
from ._analytical_feature import AnalyticalGeologicalFeature
from ._structural_frame import StructuralFrame
from .structural_frame_builder import StructuralFrameBuilder
