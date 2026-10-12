GAME_VERSION ?= BLACK2
GAME_LANGUAGE ?= ENGLISH
COMPARE ?= 1
SHIFTED ?= 0
ifneq ($(SHIFTED),0)
COMPARE := 0
endif

# NOTE: this repo is pokeblack2; the upstream config scaffold was inherited
# from pret/pokediamond. Each `ifeq ($(GAME_VERSION),...)` block below adds
# a build target. BLACk2 is the default; other Gen-IV/V titles are kept
# here as references for the porting pass and can be deleted.
ifeq ($(GAME_VERSION),BLACK2)
GAME_CODE := CPUI
BUILD_NAME := black2
TITLE_NAME := POKEMON B2
ICON_FILE := graphics/black2_icon.png
else
ifeq ($(GAME_VERSION),WHITE2)
GAME_CODE := CPVI
BUILD_NAME := white2
TITLE_NAME := POKEMON W2
ICON_FILE := graphics/white2_icon.png
else
ifeq ($(GAME_VERSION),DIAMOND)
GAME_CODE := ADA
BUILD_NAME := diamond
TITLE_NAME := POKEMON D
ICON_FILE := graphics/icon.png
else
ifeq ($(GAME_VERSION),PEARL)
GAME_CODE := APA
BUILD_NAME := pearl
TITLE_NAME := POKEMON P
ICON_FILE := graphics/icon_pearl.png
else
$(error Invalid GAME_VERSION: $(GAME_VERSION))
endif
endif
endif
endif

ifeq ($(GAME_LANGUAGE),ENGLISH)
GAME_CODE := $(GAME_CODE)E
BUILD_NAME := $(BUILD_NAME).us
GAME_REVISION := 5
else
ifeq ($(GAME_LANGUAGE),JAPANESE)
GAME_CODE := $(GAME_CODE)J
BUILD_NAME := $(BUILD_NAME).jp
GAME_REVISION := 1
else
$(error Invalid GAME_LANGUAGE: $(GAME_LANGUAGE))
endif
endif

# SECURE_CRC values for the boot ROM logo region. B2/W2 placeholders —
# verify against the corresponding .nds SHA1 in No-Intro before cutting
# a release build. Diamond/Pearl retained from the pokediamond upstream
# for reference.
ifeq ($(GAME_CODE),CPUIE)
SECURE_CRC := 0x0000  # TODO: extract from CPUIE header (look up in PRET discord)
else
ifeq ($(GAME_CODE),CPVIE)
SECURE_CRC := 0x0000  # TODO: extract from CPVIE header
else
ifeq ($(GAME_CODE),ADAE)
SECURE_CRC := 0x5931
else
ifeq ($(GAME_CODE),APAE)
SECURE_CRC := 0x014C
else
$(error Unsupported build: $(GAME_VERSION) $(GAME_LANGUAGE))
endif
endif
endif
endif

BUILD_TARGET := poke$(BUILD_NAME)

MAKE_VARS := SHIFTED=$(SHIFTED) COMPARE=$(COMPARE) GAME_LANGUAGE=$(GAME_LANGUAGE) GAME_VERSION=$(GAME_VERSION)
