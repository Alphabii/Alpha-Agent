from src.registry import register_applicator
from src.applicator.freework import FreeWorkApplicator
from src.applicator.collective import CollectiveApplicator
from src.applicator.hellowork import HelloWorkApplicator
from src.applicator.linkedin import LinkedInApplicator

register_applicator("freework", FreeWorkApplicator)
register_applicator("collective", CollectiveApplicator)
register_applicator("hellowork", HelloWorkApplicator)
register_applicator("linkedin", LinkedInApplicator)
