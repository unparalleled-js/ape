from pathlib import Path
from typing import Iterable, List

from ethpm_types.source import ContractSource

from ape.pytest.config import ConfigWrapper
from ape.types import CoverageReport, SourceTraceback
from ape.types.trace import CoverageItem
from ape.utils import ManagerAccessMixin, get_relative_path, parse_coverage_table


class CoverageData:
    def __init__(self, base_path: Path, sources: Iterable[ContractSource]):
        self.base_path = base_path

        # source_id -> id -> times hit
        self.session_coverage_report: CoverageReport = {}

        # Build coverage profile.
        for src in sources:
            if not src.source_path:
                # TODO: Handle source-less files (remote coverage)
                continue

            # Init all relevant PC hits with 0.
            statements: List[CoverageItem] = []
            for pc, item in src.pcmap.__root__.items():
                loc = item.get("location")
                if not loc and not item.get("dev"):
                    # Not a statement we can measure.
                    continue

                pc_int = int(pc)
                if pc_int < 0:
                    continue

                # Check if location already profiled.
                done = False
                for past_stmt in statements:
                    if past_stmt.location != tuple(loc):
                        continue

                    # Already tracking this location.
                    past_stmt.pcs.add(pc_int)
                    done = True
                    break

                cov_item = None
                if loc and not done:
                    # Adding a source-statement for the first time.
                    loc_tuple = (
                        int(loc[0] or -1),
                        int(loc[1] or -1),
                        int(loc[2] or -1),
                        int(loc[3] or -1),
                    )
                    cov_item = CoverageItem(location=loc_tuple, pcs={pc_int})

                elif not loc and not done:
                    # Adding a virtual statement.
                    cov_item = CoverageItem(pcs={pc_int})

                if cov_item is not None:
                    statements.append(cov_item)

            source_id = str(get_relative_path(src.source_path.absolute(), base_path.absolute()))
            self.session_coverage_report[source_id] = statements

    def cover(self, src_path: Path, pcs: Iterable[int]):
        src_id = str(get_relative_path(src_path.absolute(), self.base_path))
        if src_id not in self.session_coverage_report:
            # The source is not tracked for coverage.
            return

        for pc in pcs:
            if pc < 0:
                continue

            for stmt in self.session_coverage_report[src_id]:
                if pc in stmt.pcs:
                    stmt.hit_count += 1


class CoverageTracker(ManagerAccessMixin):
    def __init__(self, config_wrapper: ConfigWrapper):
        self.config_wrapper = config_wrapper
        sources = self.project_manager._contract_sources
        self.data = CoverageData(self.project_manager.contracts_folder, sources)

    @property
    def enabled(self) -> bool:
        return self.config_wrapper.track_coverage

    def cover(self, traceback: SourceTraceback):
        """
        Track the coverage from the given source traceback.

        Args:
            traceback (:class:`~ape.types.trace.SourceTraceback`):
              The class instance containing all the information regarding
              sources covered for a particular transaction.
        """
        for control_flow in traceback:
            source_path = control_flow.source_path
            if not source_path:
                continue

            self.data.cover(source_path, control_flow.pcs)

    def show_session_coverage(self) -> bool:
        if not self.data or not self.data.session_coverage_report:
            return False

        table = parse_coverage_table(self.data.session_coverage_report)
        self.chain_manager._reports.echo(table)
        return True
