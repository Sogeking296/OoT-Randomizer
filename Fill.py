import random
import logging
from Hints import HintArea
from State import State
from Rules import set_shop_rules
from Location import DisableType
from LocationList import location_groups
from ItemPool import remove_junk_items
from Item import ItemFactory, ItemInfo
from Search import Search

logger = logging.getLogger('')


class ShuffleError(RuntimeError):
    pass


class FillError(ShuffleError):
    pass


# Places all items into the world
def distribute_items_restrictive(window, worlds, fill_locations=None):
    song_locations = []
    for world in worlds:
        if world.settings.shuffle_song_items == 'song':
            song_location_names = location_groups['Song']
        elif world.settings.shuffle_song_items == 'dungeon':
            song_location_names = (
                'Song from Impa',
                'Deku Tree Queen Gohma Heart',
                'Dodongos Cavern King Dodongo Heart',
                'Jabu Jabus Belly Barinade Heart',
                'Forest Temple Phantom Ganon Heart',
                'Fire Temple Volvagia Heart',
                'Water Temple Morpha Heart',
                'Shadow Temple Bongo Bongo Heart',
                'Spirit Temple Twinrova Heart',
                'Sheik in Ice Cavern',
                'Bottom of the Well Lens of Truth Chest',
                'Bottom of the Well MQ Lens of Truth Chest',
                'Gerudo Training Ground Maze Path Final Chest',
                'Gerudo Training Ground MQ Ice Arrows Chest',
            )
        else:
            song_location_names = ()
        for location in song_location_names:
            try:
                song_locations.append(world.get_location(location))
            except KeyError:
                pass

    shop_locations = [location for world in worlds for location in world.get_unfilled_locations() if location.type == 'Shop' and location.price == None]

    # If not passed in, then get a shuffled list of locations to fill in
    if not fill_locations:
        fill_locations = [
            location for world in worlds for location in world.get_unfilled_locations()
            if location not in song_locations
                and location not in shop_locations
                and not location.type.startswith('Hint')]

    window.locationcount = len(fill_locations) + len(song_locations) + len(shop_locations)
    window.fillcount = 0

    # Generate the itempools
    shopitempool = [item for world in worlds for item in world.itempool if item.type == 'Shop']
    songitempool = []
    itempool     = [item for world in worlds for item in world.itempool if item.type not in ('Shop', 'Song')]

    for world in worlds:
        (itempool if world.settings.shuffle_song_items == 'any' else songitempool).extend(item for item in world.itempool if item.type == 'Song')

    # Unrestricted dungeon items are already in main item pool
    dungeon_items = [item for world in worlds for item in world.get_restricted_dungeon_items()]

    random.shuffle(itempool) # randomize item placement order. this ordering can greatly affect the location accessibility bias
    progitempool = [item for item in itempool if item.advancement]
    prioitempool = [item for item in itempool if not item.advancement and item.priority]
    restitempool = [item for item in itempool if not item.advancement and not item.priority]

    cloakable_locations = shop_locations + song_locations + fill_locations
    all_models = shopitempool + dungeon_items + songitempool + itempool
    worlds[0].settings.distribution.fill(window, worlds, [shop_locations, song_locations, fill_locations], [shopitempool, dungeon_items, songitempool, progitempool, prioitempool, restitempool])
    itempool = progitempool + prioitempool + restitempool

    # set ice traps to have the appearance of other random items in the item pool
    ice_traps = [item for item in itempool if item.name == 'Ice Trap']
    # Extend with ice traps manually placed in plandomizer
    ice_traps.extend(
        location.item for location in cloakable_locations
        if (location.has_preview()
            and location.item is not None
            and location.item.name == 'Ice Trap'
            and location.item.looks_like_item is None))
    junk_items = remove_junk_items.copy()
    junk_items.remove('Ice Trap')
    major_items = [name for name, item in ItemInfo.items.items() if item.type == 'Item' and item.advancement and item.index is not None]
    major_fake_items = []
    junk_fake_items = []
    any_fake_items = []
    if any(world.settings.ice_trap_appearance == 'major_only' for world in worlds):
        major_model_items = [item for item in itempool if item.majoritem]
        if len(major_model_items) == 0:  # All major items were somehow removed from the pool (can happen in plando)
            major_model_items = ItemFactory(major_items)
        while len(ice_traps) > len(major_fake_items):
            # if there are more ice traps than model items, then double up on model items
            major_fake_items.extend(major_model_items)
        random.shuffle(major_fake_items)
    if any(world.settings.ice_trap_appearance == 'junk_only' for world in worlds):
        junk_model_items = [item for item in itempool if item.name in junk_items]
        if len(junk_model_items) == 0:  # All junk was removed
            junk_model_items = ItemFactory(junk_items)
        while len(ice_traps) > len(junk_fake_items):
            # if there are more ice traps than model items, then double up on model items
            junk_fake_items.extend(junk_model_items)
        random.shuffle(junk_fake_items)
    if any(world.settings.ice_trap_appearance == 'anything' for world in worlds):
        any_model_items = [item for item in itempool if item.name != 'Ice Trap']
        if len(any_model_items) == 0:  # All major items and junk items were somehow removed from the pool (can happen in plando)
            any_model_items = ItemFactory(major_items) + ItemFactory(junk_items)
        while len(ice_traps) > len(any_fake_items):
            # if there are more ice traps than model items, then double up on model items
            any_fake_items.extend(any_model_items)
        random.shuffle(any_fake_items)

    for ice_trap in ice_traps:
        if ice_trap.world.settings.ice_trap_appearance == 'major_only':
            fake_item = major_fake_items.pop()
        elif ice_trap.world.settings.ice_trap_appearance == 'junk_only':
            fake_item = junk_fake_items.pop()
        else:
            fake_item = any_fake_items.pop()
        ice_trap.looks_like_item = fake_item

    # Start a search cache here.
    search = Search([world.state for world in worlds])

    # We place all the shop items first. Like songs, they have a more limited
    # set of locations that they can be placed in, so placing them first will
    # reduce the odds of creating unbeatable seeds. This also avoids needing
    # to create item rules for every location for whether they are a shop item
    # or not. This shouldn't have much affect on item bias.
    if shop_locations:
        logger.info('Placing shop items.')
        fill_ownworld_restrictive(window, worlds, search, shop_locations, shopitempool, itempool + songitempool + dungeon_items, "shop")
    # Update the shop item access rules
    for world in worlds:
        set_shop_rules(world)

    search.collect_locations()

    # If there are dungeon items that are restricted to their original dungeon,
    # we must place them first to make sure that there is always a location to
    # place them. This could probably be replaced for more intelligent item
    # placement, but will leave as is for now
    if dungeon_items:
        logger.info('Placing dungeon items.')
        fill_dungeons_restrictive(window, worlds, search, fill_locations, dungeon_items, itempool + songitempool)
        search.collect_locations()


    # If some dungeons are supposed to be empty, fill them with useless items.
    if any(world.settings.empty_dungeons_mode != 'none' for world in worlds):
        empty_locations = [location for location in fill_locations \
            if location.world.empty_dungeons[HintArea.at(location).dungeon_name].empty]
        for location in empty_locations:
            fill_locations.remove(location)
            location.world.hint_type_overrides['sometimes'].append(location.name)
            location.world.hint_type_overrides['random'].append(location.name)

        # Non-empty dungeon items may be present in restitempool but yet we
        # don't want to place them in an empty dungeon
        restdungeon, restother = [], []
        for item in restitempool:
            if item.dungeonitem and not item.unshuffled_dungeon_item:
                restdungeon.append(item)
            else:
                restother.append(item)
        fast_fill(window, empty_locations, restother)
        restitempool = restdungeon + restother
        random.shuffle(restitempool)


    # places the songs into the world
    # Currently places songs only at song locations. if there's an option
    # to allow at other locations then they should be in the main pool.
    # Placing songs on their own since they have a relatively high chance
    # of failing compared to other item type. So this way we only have retry
    # the song locations only.
    if any(world.settings.shuffle_song_items != 'any' for world in worlds):
        logger.info('Placing song items.')
        fill_ownworld_restrictive(window, worlds, search, song_locations, songitempool, progitempool, "song")
        search.collect_locations()
        fill_locations += [location for location in song_locations if location.item is None]

    # Put one item in every dungeon, needs to be done before other items are
    # placed to ensure there is a spot available for them
    if any(world.settings.one_item_per_dungeon for world in worlds):
        logger.info('Placing one major item per dungeon.')
        fill_dungeon_unique_item(window, worlds, search, fill_locations, progitempool)
        search.collect_locations()

    # Place all progression items from the main item pool.
    # Items in this group will check for reachability and will be placed
    # such that the game is guaranteed beatable.
    logger.info('Placing progression items.')
    fill_restrictive(window, worlds, search, fill_locations, progitempool)
    search.collect_locations()

    # Place all priority items.
    # These items are items that only check if the item is allowed to be
    # placed in the location, not checking reachability. This is important
    # for things like Ice Traps that can't be found at some locations
    logger.info('Placing priority items.')
    fill_restrictive_fast(window, worlds, fill_locations, prioitempool)

    # Place the rest of the items.
    # No restrictions at all. Places them completely randomly. Since they
    # cannot affect the beatability, we don't need to check them
    logger.info('Placing the rest of the items.')
    fast_fill(window, fill_locations, restitempool)

    # Log unplaced item/location warnings
    for item in progitempool + prioitempool + restitempool:
        logger.error('Unplaced Items: %s [World %d]' % (item.name, item.world.id))
    for location in fill_locations:
        logger.error('Unfilled Locations: %s [World %d]' % (location.name, location.world.id))

    if progitempool + prioitempool + restitempool:
        raise FillError('Not all items are placed.')

    if fill_locations:
        raise FillError('Not all locations have an item.')

    if not search.can_beat_game():
        raise FillError('Cannot beat game!')

    worlds[0].settings.distribution.cloak(worlds, [cloakable_locations], [all_models])

    for world in worlds:
        for location in world.get_filled_locations():
            # Get the maximum amount of wallets required to purchase an advancement item.
            if world.maximum_wallets < 3 and location.price and location.item.advancement:
                if location.price > 500:
                    world.maximum_wallets = 3
                elif world.maximum_wallets < 2 and location.price > 200:
                    world.maximum_wallets = 2
                elif world.maximum_wallets < 1 and location.price > 99:
                    world.maximum_wallets = 1


# Places restricted dungeon items into the worlds. To ensure there is room for them.
# they are placed first so it will assume all other items are reachable
def fill_dungeons_restrictive(window, worlds, search, shuffled_locations, dungeon_items, itempool):
    # List of states with all non-key items
    base_search = search.copy()
    base_search.collect_all(itempool)
    base_search.collect_locations()

    # shuffle this list to avoid placement bias
    random.shuffle(dungeon_items)

    # sort in the order Other, Small Key, Boss Key before placing dungeon items
    # python sort is stable, so the ordering is still random within groups
    # fill_restrictive processes the resulting list backwards so the Boss Keys will actually be placed first
    sort_order = {"BossKey": 3, "GanonBossKey": 3, "SmallKey": 2}
    dungeon_items.sort(key=lambda item: sort_order.get(item.type, 1))

    # place dungeon items
    fill_restrictive(window, worlds, base_search, shuffled_locations, dungeon_items)


# Places items into dungeon locations. This is used when there should be exactly
# one progression item per dungeon. This should be ran before all the progression
# items are places to ensure there is space to place them.
def fill_dungeon_unique_item(window, worlds, search, fill_locations, itempool):
    # We should make sure that we don't count event items, shop items,
    # token items, or dungeon items as a major item. itempool at this
    # point should only be able to have tokens of those restrictions
    # since the rest are already placed.
    major_items = [item for item in itempool if item.majoritem]
    minor_items = [item for item in itempool if not item.majoritem]

    dungeons = [
        dungeon
        for world in worlds
        if world.settings.one_item_per_dungeon
        and world.settings.empty_dungeons_mode != 'none'
        for dungeon in world.dungeons
        if not world.empty_dungeons[dungeon.name].empty
    ]

    double_dungeons = []
    for dungeon in dungeons:
        # we will count spirit temple twice so that it gets 2 items to match vanilla
        if dungeon.name == 'Spirit Temple':
            double_dungeons.append(dungeon)
    dungeons.extend(double_dungeons)

    random.shuffle(dungeons)
    random.shuffle(itempool)

    base_search = search.copy()
    base_search.collect_all(minor_items)
    base_search.collect_locations()
    all_dungeon_locations = []

    # iterate of all the dungeons in a random order, placing the item there
    for dungeon in dungeons:
        # Need to re-get dungeon regions to ensure boss rooms are considered
        regions = []
        for region in dungeon.world.regions:
            try:
                if HintArea.at(region).dungeon_name == dungeon.name:
                    regions.append(region)
            except:
                pass
        dungeon_locations = [location for region in regions for location in region.locations if location in fill_locations]

        # cache this list to flag afterwards
        all_dungeon_locations.extend(dungeon_locations)

        # Sort major items in such a way that they are placed first if dungeon restricted.
        # There still won't be enough locations for small keys in one item per dungeon mode, though.
        for item in list(major_items):
            if not item.world.get_region('Root').can_fill(item):
                major_items.remove(item)
                major_items.append(item)

        # place 1 item into the dungeon
        fill_restrictive(window, worlds, base_search, dungeon_locations, major_items, 1)

        # update the location and item pool, removing any placed items and filled locations
        # the fact that you can remove items from a list you're iterating over is python magic
        for item in itempool:
            if item.location != None:
                fill_locations.remove(item.location)
                itempool.remove(item)

    # flag locations to not place further major items. it's important we do it on the
    # locations instead of the dungeon because some locations are not in the dungeon
    for location in all_dungeon_locations:
        location.minor_only = True

    # Error out if we have any items that won't be placeable in the overworld left.
    for item in major_items:
        if not item.world.get_region('Root').can_fill(item):
            raise FillError(f"No more dungeon locations available for {item.name} to be placed with 'Dungeons Have One Major Item' enabled.")

    logger.info("Unique dungeon items placed")


# Places items restricting placement to the recipient player's own world
def fill_ownworld_restrictive(window, worlds, search, locations, ownpool, itempool, description="Unknown", attempts=15):
    # get the locations for each world

    # look for preplaced items
    placed_prizes = [loc.item.name for loc in locations if loc.item is not None]
    unplaced_prizes = [item for item in ownpool if item.name not in placed_prizes]
    empty_locations = [loc for loc in locations if loc.item is None]

    prizepool_dict = {world.id: [item for item in unplaced_prizes if item.world.id == world.id] for world in worlds}
    prize_locs_dict = {world.id: [loc for loc in empty_locations if loc.world.id == world.id] for world in worlds}

    # Shop item being sent in to this method are tied to their own world.
    # Therefore, let's do this one world at a time. We do this to help
    # increase the chances of successfully placing songs
    for world in worlds:
        # List of states with all items
        unplaced_prizes = [item for item in unplaced_prizes if item not in prizepool_dict[world.id]]
        base_search = search.copy()
        base_search.collect_all(itempool + unplaced_prizes)

        world_attempts = attempts
        while world_attempts:
            world_attempts -= 1
            try:
                prizepool = list(prizepool_dict[world.id])
                prize_locs = list(prize_locs_dict[world.id])
                random.shuffle(prizepool)
                fill_restrictive(window, worlds, base_search, prize_locs, prizepool)

                logger.info("Placed %s items for world %s.", description, (world.id+1))
            except FillError as e:
                logger.info("Failed to place %s items for world %s. Will retry %s more times.", description, (world.id+1), world_attempts)
                for location in prize_locs_dict[world.id]:
                    location.item = None
                    location.price = None
                    if location.disabled == DisableType.DISABLED:
                        location.disabled = DisableType.PENDING
                logger.info('\t%s' % str(e))
                continue
            break
        else:
            raise FillError('Unable to place %s items in world %d' % (description, (world.id+1)))



# Places items in the itempool into locations.
# worlds is a list of worlds and is redundant of the worlds in the base_state_list
# base_state_list is a list of world states prior to placing items in the item pool
# items and locations have pointers to the world that they belong to
#
# The algorithm places items in the world in reverse.
# This means we first assume we have every item in the item pool and
# remove an item and try to place it somewhere that is still reachable
# This method helps distribution of items locked behind many requirements
#
# count is the number of items to place. If count is negative, then it will place
# every item. Raises an error if specified count of items are not placed.
#
# This function will modify the location and itempool arguments. placed items and
# filled locations will be removed. If this returns and error, then the state of
# those two lists cannot be guaranteed.
def fill_restrictive(window, worlds, base_search, locations, itempool, count=-1):
    unplaced_items = []

    # don't run over this search, just keep it as an item collection
    items_search = base_search.copy()
    items_search.collect_all(itempool)
    logging.getLogger('').debug(f'Placing {len(itempool)} items among {len(locations)} potential locations.')
    itempool.sort(key=lambda item: not item.priority)

    # loop until there are no items or locations
    while itempool and locations:
        # if remaining count is 0, return. Negative means unbounded.
        if count == 0:
            break

        # get an item and remove it from the itempool
        item_to_place = itempool.pop()
        if item_to_place.priority:
            l2cations = [l for l in locations if l.can_fill_fast(item_to_place)]
        elif item_to_place.majoritem:
            l2cations = [l for l in locations if not l.minor_only]
        else:
            l2cations = locations
        random.shuffle(l2cations)

        # generate the max search with every remaining item
        # this will allow us to place this item in a reachable location
        items_search.uncollect(item_to_place)
        max_search = items_search.copy()
        max_search.collect_locations()

        # perform_access_check checks location reachability
        predicates = []
        for world in worlds:
            if world.check_beatable_only:
                if world.settings.reachable_locations == 'goals':
                    # If this item is required for a goal, it must be placed somewhere reachable.
                    # We also need to check to make sure the game is beatable, since custom goals might not imply that.
                    predicates.append(lambda state: state.won() and state.has_all_item_goals())
                else:
                    # If the game is not beatable without this item, it must be placed somewhere reachable.
                    predicates.append(State.won)
            else:
                # All items must be placed somewhere reachable.
                perform_access_check = True
                break
        else:
            perform_access_check = not max_search.can_beat_game(scan_for_items=False, predicates=predicates)

        # find a location that the item can be placed. It must be a valid location
        # in the world we are placing it (possibly checking for reachability)
        spot_to_fill = None
        for location in l2cations:
            if location.can_fill(max_search.state_list[location.world.id], item_to_place, perform_access_check):
                # for multiworld, make it so that the location is also reachable
                # in the world the item is for. This is to prevent early restrictions
                # in one world being placed late in another world. If this is not
                # done then one player may be waiting a long time for other players.
                if location.world.id != item_to_place.world.id:
                    try:
                        source_location = item_to_place.world.get_location(location.name)
                        if not source_location.can_fill(max_search.state_list[item_to_place.world.id], item_to_place, perform_access_check):
                            # location wasn't reachable in item's world, so skip it
                            continue
                    except KeyError:
                        # This location doesn't exist in the other world, let's look elsewhere.
                        # Check access to whatever parent region exists in the other world.
                        can_reach = True
                        parent_region = location.parent_region
                        while parent_region:
                            try:
                                source_region = item_to_place.world.get_region(parent_region.name)
                                can_reach = max_search.can_reach(source_region)
                                break
                            except KeyError:
                                parent_region = parent_region.entrances[0].parent_region
                        if not can_reach:
                            continue

                if location.disabled == DisableType.PENDING:
                    if not max_search.can_beat_game(False):
                        continue
                    location.disabled = DisableType.DISABLED

                # location is reachable (and reachable in item's world), so place item here
                spot_to_fill = location
                break

        # if we failed to find a suitable location
        if spot_to_fill is None:
            # if we specify a count, then we only want to place a subset, so a miss might be ok
            if count > 0:
                # don't decrement count, we didn't place anything
                unplaced_items.append(item_to_place)
                items_search.collect(item_to_place)
                continue
            else:
                # we expect all items to be placed
                raise FillError(f'Game unbeatable: No more spots to place {item_to_place} [World {item_to_place.world.id + 1}] from {len(l2cations)} locations ({len(locations)} total); {len(itempool)} other items left to place, plus {len(unplaced_items)} skipped')

        # Place the item in the world and continue
        spot_to_fill.world.push_item(spot_to_fill, item_to_place)
        locations.remove(spot_to_fill)
        window.fillcount += 1
        window.update_progress(5 + ((window.fillcount / window.locationcount) * 30))

        # decrement count
        count -= 1

    # assert that the specified number of items were placed
    if count > 0:
        raise FillError('Could not place the specified number of item. %d remaining to be placed.' % count)
    if count < 0 and len(itempool) > 0:
        raise FillError('Could not place all the items. %d remaining to be placed.' % len(itempool))
    # re-add unplaced items that were skipped
    itempool.extend(unplaced_items)


# This places items in the itempool into the locations
# It does not check for reachability, only that the item is
# allowed in the location
def fill_restrictive_fast(window, worlds, locations, itempool):
    while itempool and locations:
        item_to_place = itempool.pop()
        random.shuffle(locations)

        # get location that allows this item
        spot_to_fill = None
        for location in locations:
            if location.can_fill_fast(item_to_place):
                spot_to_fill = location
                break

        # if we failed to find a suitable location, then stop placing items
        # we don't need to check beatability since world must be beatable
        # at this point
        if spot_to_fill is None:
            if not all(world.check_beatable_only for world in worlds):
                logger.debug('Not all items placed. Game beatable anyway.')
            break

        # Place the item in the world and continue
        spot_to_fill.world.push_item(spot_to_fill, item_to_place)
        locations.remove(spot_to_fill)
        window.fillcount += 1
        window.update_progress(5 + ((window.fillcount / window.locationcount) * 30))


# this places item in item_pool completely randomly into
# fill_locations. There is no checks for validity since
# there should be none for these remaining items
def fast_fill(window, locations, itempool):
    random.shuffle(locations)
    while itempool and locations:
        spot_to_fill = locations.pop()
        item_to_place = itempool.pop()
        spot_to_fill.world.push_item(spot_to_fill, item_to_place)
        window.fillcount += 1
        window.update_progress(5 + ((window.fillcount / window.locationcount) * 30))
