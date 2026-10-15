"""English operational events; UI messages and prompts stay separate."""
import logging

LOG = logging.getLogger('Star7Director')
STAGES = {'601':'conditioning', '127':'base_sampling', '376':'hd_refinement',
          '395':'face_refinement', '377':'av_decode', '150':'video_encode',
          '602':'base_cache', '604':'complete'}


def event(name, level=logging.INFO, **fields):
    # repr keeps newlines in external error messages from breaking event lines.
    LOG.log(level, '[Star7 Director] %s | %s', name,
            ' '.join(f'{key}={value!r}' for key, value in fields.items()))


class DirectorExecutionError(ValueError):
    """One origin label, propagated unchanged through dependent steps."""
    def __init__(self, stage, node, error):
        super().__init__(f'Star7 Director: {stage} failed (node={node}, '
                         f'error={type(error).__name__}): {error}')
