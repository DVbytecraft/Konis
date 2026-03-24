"""
api.serializers — point d'entrée unique.

Les imports existants (from api.serializers import XSerializer) continuent
de fonctionner sans modification.
"""
from .collecte import CollecteArgentCreateSerializer, CollecteArgentSerializer
from .core import (
    EntrepriseSerializer,
    FactoryCreateSerializer,
    FactorySerializer,
    FactoryUpdateSerializer,
    FactoryUserSerializer,
    LieuMinimalSerializer,
    LieuSerializer,
    UserMinimalSerializer,
    UserSerializer,
)
from .depenses import CategorieDepenseSerializer, DepenseSerializer
from .inventaire import (
    BoutiqueStockReceiptSerializer,
    MouvementStockSerializer,
    StockSerializer,
    TransfertCreateSerializer,
    TransfertSerializer,
)
from .mpsl import AchatMPSLBatchSerializer, AchatMPSLCreateSerializer, AchatMPSLSerializer, TransfertMPSLCreateSerializer
from .produits import CategorieSerializer, ProduitMinimalSerializer, ProduitSerializer
from .usine import (
    AchatUsineCreateSerializer,
    AchatUsineSerializer,
    LotProductionCreateSerializer,
    LotProductionSerializer,
    TransfertCessionCreateSerializer,
    TransfertCessionSerializer,
    TransfertDirectUsineCreateSerializer,
    TransfertInterUsineCreateSerializer,
    TransfertInterUsineSerializer,
)
from .ventes import (
    FactureCreateSerializer,
    FactureSerializer,
    LigneFactureSerializer,
    LigneVenteSerializer,
    MoutureSeuleSerializer,
    TicketReprintCreateSerializer,
    TicketSerializer,
    VenteBoutiqueCreateSerializer,
)

__all__ = [
    # core
    "EntrepriseSerializer",
    "FactoryCreateSerializer",
    "FactorySerializer",
    "FactoryUpdateSerializer",
    "FactoryUserSerializer",
    "LieuMinimalSerializer",
    "LieuSerializer",
    "UserMinimalSerializer",
    "UserSerializer",
    # produits
    "CategorieSerializer",
    "ProduitMinimalSerializer",
    "ProduitSerializer",
    # inventaire
    "BoutiqueStockReceiptSerializer",
    "MouvementStockSerializer",
    "StockSerializer",
    "TransfertCreateSerializer",
    "TransfertSerializer",
    # ventes
    "FactureCreateSerializer",
    "FactureSerializer",
    "LigneFactureSerializer",
    "LigneVenteSerializer",
    "MoutureSeuleSerializer",
    "TicketReprintCreateSerializer",
    "TicketSerializer",
    "VenteBoutiqueCreateSerializer",
    # depenses
    "CategorieDepenseSerializer",
    "DepenseSerializer",
    # usine
    "AchatUsineCreateSerializer",
    "AchatUsineSerializer",
    "LotProductionCreateSerializer",
    "LotProductionSerializer",
    "TransfertCessionCreateSerializer",
    "TransfertCessionSerializer",
    "TransfertDirectUsineCreateSerializer",
    "TransfertInterUsineCreateSerializer",
    "TransfertInterUsineSerializer",
    # mpsl
    "AchatMPSLBatchSerializer",
    "AchatMPSLCreateSerializer",
    "AchatMPSLSerializer",
    "TransfertMPSLCreateSerializer",
    # collecte
    "CollecteArgentCreateSerializer",
    "CollecteArgentSerializer",
]
