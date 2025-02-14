import random as rd

# import scipy as sc
import scipy.stats as sct

import numpy as np

from ...utils import getLogger

logger = getLogger(__name__)


def geometric_scaling_parameters(intrusion_type):

    geom_scaling_a_avg = {
        "plutons": 0.81,
        "laccoliths": 0.92,
        "major_mafic_sills": 0.85,
        "mesoscale_mafic_sills": 0.49,
        "minor_mafic_sills": 0.91,
    }
    geom_scaling_a_stdv = {
        "plutons": 0.12,
        "laccoliths": 0.11,
        "major_mafic_sills": 0.1,
        "mesoscale_mafic_sills": 0.13,
        "minor_mafic_sills": 0.25,
    }
    geom_scaling_b_avg = {
        "plutons": 1.08,
        "laccoliths": 0.12,
        "major_mafic_sills": 0.01,
        "mesoscale_mafic_sills": 0.47,
        "minor_mafic_sills": 0.27,
    }
    geom_scaling_b_stdv = {
        "plutons": 1.38,
        "laccoliths": 0.02,
        "major_mafic_sills": 0.02,
        "mesoscale_mafic_sills": 0.33,
        "minor_mafic_sills": 0.04,
    }

    a_avg = geom_scaling_a_avg.get(intrusion_type)
    a_stdv = geom_scaling_a_stdv.get(intrusion_type)
    b_avg = geom_scaling_b_avg.get(intrusion_type)
    b_stdv = geom_scaling_b_stdv.get(intrusion_type)

    return a_avg, a_stdv, b_avg, b_stdv


def thickness_from_geometric_scaling(length, intrusion_type):

    a_avg, a_stdv, b_avg, b_stdv = geometric_scaling_parameters(intrusion_type)

    n_realizations = 10000
    maxT = 0
    a = sct.norm.ppf(np.random.rand(n_realizations), loc=a_avg, scale=a_stdv)
    b = sct.norm.ppf(np.random.rand(n_realizations), loc=b_avg, scale=b_stdv)
    maxT = b * np.power(length, a)
    maxT[maxT < 0] = None
    mean_t = np.nanmean(maxT)

    logger.info("Building intrusion of thickness {}".format(mean_t))

    return mean_t


def contact_pts_using_geometric_scaling(thickness, points_df, inflation_vector):

    translation_vector = (
        inflation_vector
        / np.linalg.norm(inflation_vector, axis=1).reshape(1, len(inflation_vector)).T
    ) * thickness
    points_translated = points_df.loc[:, ["X", "Y", "Z"]].copy() + translation_vector
    points_translated_xyz = points_translated.to_numpy()

    return points_translated, points_translated_xyz
